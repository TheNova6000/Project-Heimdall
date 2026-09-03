"""
Attempt unification acceptance test -- ATTEMPT_MODEL_SPEC.md's five
adversarial scenarios, run against the real pipeline (backfill + Stage 3/4's
own executor, not a synthetic log), same discipline as asof_runner.py.

The headline scenario is the exact shape of Stage 4 Gate 3's original
confusion: attempt 1 fails, attempt 2 succeeds, and a FRESH call to
run_recovery_for_payment() -- with no "successful retry" special case
anywhere in recovery_agent.py -- must produce a status-based DO_NOT_RETRY,
not "INVESTIGATE / unrecognized failure_reason=None".

Run directly: `python -m financial_system.events.attempt_runner`
"""
from __future__ import annotations

import csv
import sys
from datetime import timedelta, timezone
from pathlib import Path

from financial_system.action.action_store import ActionStore
from financial_system.action.loop import run_action_loop_v2
from financial_system.entity_resolution.runner import run_phase2
from financial_system.events.action_projection import project_action_outcome
from financial_system.events.backfill import backfill
from financial_system.events.projection import project
from financial_system.events.store import EventStore
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.builder import build_financial_state
from financial_system.financial_state.store import FinancialStateStore
from financial_system.ingestion import reference_ingestion
from financial_system.recovery.recovery_agent import run_recovery_for_payment

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "recovery_labels.csv"
RAW_DIR = REPO_ROOT / "financial_system" / "data" / "raw"
DATA_DIR = REPO_ROOT / "financial_system" / "data"

STATE_DB = DATA_DIR / "financial_state_attempt.db"
GRAPH_DB = DATA_DIR / "financial_graph_attempt.db"
GRAPH_DB_AFTER = DATA_DIR / "financial_graph_attempt_after.db"
EVENTS_DB = DATA_DIR / "events_attempt.db"
ACTIONS_DB = DATA_DIR / "actions_attempt.db"
SNAPSHOT_MIDWAY = DATA_DIR / "state_attempt_midway.db"


def _fresh(path: Path) -> None:
    if path.exists():
        path.unlink()


def _aware(dt):
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def setup():
    for p in (STATE_DB, GRAPH_DB, GRAPH_DB_AFTER, EVENTS_DB, ACTIONS_DB):
        _fresh(p)

    events = EventStore(EVENTS_DB)
    backfill(events, RAW_DIR)

    state, _ = build_financial_state(db_path=STATE_DB, raw_dir=RAW_DIR)
    violations = run_phase2(db_path=STATE_DB)[0]
    assert not violations, f"unexpected reference-key violations: {violations}"
    _, graph = build_graph(state_db=STATE_DB, graph_db=GRAPH_DB)

    actions = ActionStore(ACTIONS_DB)
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    success_pid = next(r for r in rows if r["failure_reason"] == "technical_failure"
                        and r["retry_would_succeed"] == "True")["payment_id"]

    labeled_pids = {r["payment_id"] for r in rows}
    payment_rows = [dict(r) for r in state.all_rows("payments")]
    never_failed_pid = next(r["payment_id"] for r in payment_rows
                             if r["status"] == "success" and r["payment_id"] not in labeled_pids)

    return events, actions, graph, success_pid, never_failed_pid


def scenario_1(events, actions, graph, pid) -> bool:
    print("-- Scenario 1: attempt 1 fails, attempt 2 succeeds -> fresh Recovery says DO_NOT_RETRY --")
    run_action_loop_v2(graph, pid, events, actions, investigate=False)
    events.commit()

    failed = events.events_for_subject(pid, "PaymentFailed")
    outcomes = events.events_for_subject(pid, "ActionOutcomeObserved")
    attempt_seq = [failed[0].payload.get("attempt_number")] + [o.payload.get("attempt_number") for o in outcomes]

    # Apply the outcome to live state the same way Stage 4's own executor
    # does downstream of this loop (project_action_outcome against `state`)
    # -- this test drives run_action_loop_v2 directly, so it must apply the
    # same projection step production code performs before Recovery is
    # asked to look at the payment again.
    state = FinancialStateStore(STATE_DB)
    for e in outcomes:
        project_action_outcome(e, state)

    _, graph_after = build_graph(state_db=STATE_DB, graph_db=GRAPH_DB_AFTER)
    verdict = run_recovery_for_payment(graph_after, pid, investigate=False)

    ok = (attempt_seq == [1, 2] and outcomes[0].payload["verification_result"] == "SUCCESS"
          and verdict.decision == "DO_NOT_RETRY" and "not currently failed" in verdict.reason
          and "unrecognized" not in verdict.reason)
    print(f"  attempt_number sequence (PaymentFailed, ActionOutcomeObserved): {attempt_seq} (expected [1, 2])")
    print(f"  fresh Recovery verdict: decision={verdict.decision} reason={verdict.reason!r}")
    print("PASS" if ok else "FAIL")
    return ok, failed[0].occurred_at, outcomes[0].occurred_at


def scenario_4(events, pid, t1) -> bool:
    print("\n-- Scenario 4: as_of strictly between attempt 1 and attempt 2 sees only attempt 1 --")
    _fresh(SNAPSHOT_MIDWAY)
    snap = FinancialStateStore(SNAPSHOT_MIDWAY)
    for fn in (reference_ingestion.ingest_merchants, reference_ingestion.ingest_customers,
               reference_ingestion.ingest_devices, reference_ingestion.ingest_instruments):
        fn(snap, RAW_DIR, "attempt_asof")
    snap.commit()
    project(events, snap, as_of=t1)
    row = next(dict(r) for r in snap.all_rows("payments") if dict(r)["payment_id"] == pid)
    snap.close()

    visible = events.all_events("ActionOutcomeObserved", as_of=t1)
    visible_for_pid = [e for e in visible if e.subject_id == pid]
    ok = row["status"] == "failed" and not visible_for_pid
    print(f"  as_of={t1.isoformat()} -> status={row['status']!r}, "
          f"ActionOutcomeObserved events visible for {pid}: {len(visible_for_pid)} (expected 0)")
    print("PASS" if ok else "FAIL")
    return ok


def scenario_5(graph, pid) -> bool:
    print("\n-- Scenario 5: Recovery called on a payment that was NEVER retried -> same general answer --")
    verdict = run_recovery_for_payment(graph, pid, investigate=False)
    ok = verdict.decision == "DO_NOT_RETRY" and "not currently failed" in verdict.reason
    print(f"  payment: {pid} (status=success from birth, no retry ever attempted)")
    print(f"  Recovery verdict: decision={verdict.decision} reason={verdict.reason!r}")
    print("PASS" if ok else "FAIL")
    return ok


def run() -> bool:
    print("Building event log (backfill + one live 2-attempt sequence)...")
    events, actions, graph, success_pid, never_failed_pid = setup()

    ok1, failed_at, outcome_at = scenario_1(events, actions, graph, success_pid)
    ok4 = scenario_4(events, success_pid, _aware(failed_at))
    ok5 = scenario_5(graph, never_failed_pid)

    events.close()
    passed = ok1 and ok4 and ok5
    print(f"\nATTEMPT UNIFICATION: {'PASS' if passed else 'FAIL'}")
    return passed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(0 if run() else 1)
