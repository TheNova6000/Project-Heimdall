"""
as_of projection acceptance test -- TEMPORAL_MODEL_SPEC.md's "as_of
projection semantics" section, marked "Not implemented" until now. Proves
the invariant that section names: project(events, as_of=T) must produce
exactly the state that would exist if only events with occurred_at <= T
had been observed -- against a real event log (backfilled CSV history plus
one genuine live retry success from Stage 3/4's own executor), not a
synthetic shortcut.

One EventStore, replayed into four independently-built FinancialStateStore
snapshots (T1 before the retry, T2 exactly at it, T3 comfortably after,
and "current" with no as_of at all) -- proving multiple historical views
come from ONE event log, never a second store per snapshot in spirit; the
event log itself is never duplicated, only replayed.

Run directly: `python -m financial_system.events.asof_runner`
"""
from __future__ import annotations

import csv
import sys
from datetime import timedelta
from pathlib import Path

from financial_system.action.action_store import ActionStore
from financial_system.action.loop import run_action_loop_v2
from financial_system.entity_resolution.runner import run_phase2
from financial_system.events.backfill import backfill
from financial_system.events.projection import project
from financial_system.events.store import EventStore
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.builder import build_financial_state
from financial_system.financial_state.store import FinancialStateStore
from financial_system.ingestion import reference_ingestion

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "recovery_labels.csv"
RAW_DIR = REPO_ROOT / "financial_system" / "data" / "raw"
DATA_DIR = REPO_ROOT / "financial_system" / "data"

STATE_DB = DATA_DIR / "financial_state_asof.db"
GRAPH_DB = DATA_DIR / "financial_graph_asof.db"
EVENTS_DB = DATA_DIR / "events_asof.db"
ACTIONS_DB = DATA_DIR / "actions_asof.db"

SNAPSHOTS = {
    "t1_before_retry": DATA_DIR / "state_asof_t1.db",
    "t2_at_retry": DATA_DIR / "state_asof_t2.db",
    "t3_after_retry": DATA_DIR / "state_asof_t3.db",
    "current_no_as_of": DATA_DIR / "state_asof_current.db",
}


def _fresh(path: Path) -> None:
    if path.exists():
        path.unlink()


def setup():
    """One EventStore: full backfilled log + one genuine live retry
    success, built the same way Stage 1 (backfill) and Stage 3/4 (live
    retry via run_action_loop_v2) already build it -- as_of is only
    meaningful proven against the real pipeline, not a hand-built log."""
    for p in (STATE_DB, GRAPH_DB, EVENTS_DB, ACTIONS_DB):
        _fresh(p)

    events = EventStore(EVENTS_DB)
    backfill(events, RAW_DIR)

    state, _ = build_financial_state(db_path=STATE_DB, raw_dir=RAW_DIR)
    violations = run_phase2(db_path=STATE_DB)[0]
    assert not violations, f"unexpected reference-key violations: {violations}"
    _, graph = build_graph(state_db=STATE_DB, graph_db=GRAPH_DB)

    actions = ActionStore(ACTIONS_DB)
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        row = next(r for r in csv.DictReader(f)
                   if r["failure_reason"] == "technical_failure" and r["retry_would_succeed"] == "True")
    pid = row["payment_id"]

    run_action_loop_v2(graph, pid, events, actions, investigate=False)
    events.commit()

    outcomes = events.events_for_subject(pid, "ActionOutcomeObserved")
    assert len(outcomes) == 1 and outcomes[0].payload["verification_result"] == "SUCCESS", (
        f"setup expected exactly one SUCCESS outcome for {pid}, got {[e.payload for e in outcomes]}"
    )
    outcome_at = outcomes[0].occurred_at

    failed = events.events_for_subject(pid, "PaymentFailed")
    assert len(failed) == 1
    failed_at = failed[0].occurred_at
    # EventStore.append() now normalizes occurred_at/recorded_at to aware UTC
    # at the write boundary (the recorded_at >= occurred_at checkpoint), so
    # backfilled (originally-naive) and live (originally-aware) timestamps
    # read back from the store already compare directly -- no per-caller
    # workaround needed here anymore.
    assert failed_at.tzinfo is not None and outcome_at.tzinfo is not None
    assert failed_at < outcome_at, "backfilled failure must precede the live retry outcome"

    return events, pid, failed_at, outcome_at


def _payment_row(state: FinancialStateStore, pid: str) -> dict:
    return next(dict(r) for r in state.all_rows("payments") if dict(r)["payment_id"] == pid)


def _snapshot(events: EventStore, path: Path, as_of, run_id: str, pid: str) -> dict:
    """Builds ONE fresh, independent state snapshot at as_of from the SAME
    EventStore, returns the projected payment row. No two snapshots share
    a store; the only thing shared across all of them is the event log."""
    _fresh(path)
    snap = FinancialStateStore(path)
    for fn in (reference_ingestion.ingest_merchants, reference_ingestion.ingest_customers,
               reference_ingestion.ingest_devices, reference_ingestion.ingest_instruments):
        fn(snap, RAW_DIR, run_id)
    snap.commit()
    project(events, snap, as_of=as_of)
    row = _payment_row(snap, pid)
    snap.close()  # Windows file-lock discipline, same as adversarial_test.py
    return row


def run() -> bool:
    print("Building event log (backfill + one live retry success)...")
    events, pid, failed_at, outcome_at = setup()
    events_before = events.count()
    print(f"  subject payment: {pid}")
    print(f"  PaymentFailed occurred_at:        {failed_at.isoformat()}")
    print(f"  ActionOutcomeObserved occurred_at: {outcome_at.isoformat()}")

    t1 = failed_at
    t2 = outcome_at
    t3 = outcome_at + timedelta(hours=1)

    print("\n-- Gate 1: T < outcome -> payment still reflects the failure --")
    row_t1 = _snapshot(events, SNAPSHOTS["t1_before_retry"], t1, "asof_t1", pid)
    gate1 = row_t1["status"] == "failed" and row_t1["failure_reason"] is not None and row_t1["captured_at"] is None
    print(f"  as_of={t1.isoformat()} -> status={row_t1['status']!r} failure_reason={row_t1['failure_reason']!r} "
          f"captured_at={row_t1['captured_at']!r}")
    print("GATE 1: PASS" if gate1 else "GATE 1: FAIL")

    print("\n-- Gate 2: T = outcome -> payment reflects the outcome (inclusive boundary) --")
    row_t2 = _snapshot(events, SNAPSHOTS["t2_at_retry"], t2, "asof_t2", pid)
    gate2 = row_t2["status"] == "success" and row_t2["failure_reason"] is None
    print(f"  as_of={t2.isoformat()} -> status={row_t2['status']!r} failure_reason={row_t2['failure_reason']!r}")
    print("GATE 2: PASS" if gate2 else "GATE 2: FAIL")

    print("\n-- Gate 3: T > outcome -> payment reflects the outcome --")
    row_t3 = _snapshot(events, SNAPSHOTS["t3_after_retry"], t3, "asof_t3", pid)
    gate3 = row_t3["status"] == "success" and row_t3["failure_reason"] is None
    print(f"  as_of={t3.isoformat()} -> status={row_t3['status']!r} failure_reason={row_t3['failure_reason']!r}")
    print("GATE 3: PASS" if gate3 else "GATE 3: FAIL")

    print("\n-- Gate 4: no as_of (current) matches T3, and one event log produced all four snapshots --")
    row_current = _snapshot(events, SNAPSHOTS["current_no_as_of"], None, "asof_current", pid)
    events_after = events.count()
    gate4 = (row_current["status"] == row_t3["status"] == "success"
              and row_current["failure_reason"] == row_t3["failure_reason"] is None
              and events_after == events_before)
    print(f"  as_of=None -> status={row_current['status']!r} failure_reason={row_current['failure_reason']!r}")
    print(f"  event log count: {events_before} before snapshots, {events_after} after "
          f"[{'OK, unchanged' if events_after == events_before else 'FAIL, mutated'}]")
    print("GATE 4: PASS" if gate4 else "GATE 4: FAIL")

    events.close()
    passed = gate1 and gate2 and gate3 and gate4
    print(f"\nAS_OF PROJECTION: {'PASS' if passed else 'FAIL'}")
    return passed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(0 if run() else 1)
