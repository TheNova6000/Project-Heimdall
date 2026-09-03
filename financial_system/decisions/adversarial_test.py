"""
Adversarial test for DECISION_PROVENANCE_SPEC.md's DecisionRecord --
proves the historical-reconstruction guarantee the spec claims, precisely
as scoped: "same decision reproduced when entity resolution hasn't
changed," not "no matter what" (the spec's own honesty about
entity_matches not being pinned by world_as_of).

Run directly: `python -m financial_system.decisions.adversarial_test`
"""
from __future__ import annotations

import csv
import sys
from datetime import timezone
from pathlib import Path

from financial_system.action.action_store import ActionStore
from financial_system.action.loop import run_action_loop_v2
from financial_system.decisions.store import DecisionStore
from financial_system.entity_resolution.runner import run_phase2
from financial_system.events.backfill import backfill
from financial_system.events.projection import project
from financial_system.events.store import EventStore
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.builder import build_financial_state
from financial_system.financial_state.store import FinancialStateStore
from financial_system.ingestion import reference_ingestion
from financial_system.policy.rules import POLICY_RULES_VERSION
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.recovery.signals import RECOVERY_LOGIC_VERSION

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "recovery_labels.csv"
RAW_DIR = REPO_ROOT / "financial_system" / "data" / "raw"
DATA_DIR = REPO_ROOT / "financial_system" / "data"

STATE_DB = DATA_DIR / "financial_state_decisions.db"
GRAPH_DB = DATA_DIR / "financial_graph_decisions.db"
EVENTS_DB = DATA_DIR / "events_decisions.db"
ACTIONS_DB = DATA_DIR / "actions_decisions.db"
DECISIONS_DB = DATA_DIR / "decisions_decisions.db"
REPLAY_STATE_DB = DATA_DIR / "financial_state_decisions_replay.db"
REPLAY_GRAPH_DB = DATA_DIR / "financial_graph_decisions_replay.db"


def _fresh(path: Path) -> None:
    if path.exists():
        path.unlink()


def setup():
    for p in (STATE_DB, GRAPH_DB, EVENTS_DB, ACTIONS_DB, DECISIONS_DB):
        _fresh(p)
    events = EventStore(EVENTS_DB)
    backfill(events, RAW_DIR)
    state, _ = build_financial_state(db_path=STATE_DB, raw_dir=RAW_DIR)
    violations = run_phase2(db_path=STATE_DB)[0]
    assert not violations
    _, graph = build_graph(state_db=STATE_DB, graph_db=GRAPH_DB)
    actions = ActionStore(ACTIONS_DB)
    decisions = DecisionStore(DECISIONS_DB)
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    retry_pid = next(r for r in rows if r["failure_reason"] == "technical_failure"
                      and r["retry_would_succeed"] == "True")["payment_id"]
    review_pid = next(r for r in rows if r["failure_reason"] == "insufficient_funds")["payment_id"]
    return events, actions, decisions, graph, retry_pid, review_pid


def test_consequential_decision_recorded(events, actions, decisions, graph, pid) -> bool:
    print("-- 1. A consequential decision (policy ALLOW -> Action) is recorded --")
    case = run_action_loop_v2(graph, pid, events, actions, investigate=False, decisions=decisions)
    records = decisions.all_for_subject(pid)
    ok = (len(records) == 1 and records[0].policy_outcome == "ALLOW"
          and records[0].agent == "recovery" and records[0].action_id is not None
          and records[0].logic_version == RECOVERY_LOGIC_VERSION
          and records[0].policy_version == POLICY_RULES_VERSION)
    print(f"  case_status={case.case_status}, DecisionRecords for {pid}: {len(records)}")
    if records:
        r = records[0]
        print(f"  decision={r.decision} policy_outcome={r.policy_outcome} rule={r.policy_rule_id} "
              f"action_id={r.action_id[:8] if r.action_id else None} "
              f"logic_version={r.logic_version} policy_version={r.policy_version}")
    print("PASS" if ok else "FAIL")
    return ok, records[0] if records else None


def test_non_consequential_decision_not_recorded(events, actions, decisions, graph, pid) -> bool:
    print("\n-- 2. A non-consequential decision (REVIEW, no Action authorized) is NOT recorded --")
    case = run_action_loop_v2(graph, pid, events, actions, investigate=False, decisions=decisions)
    records = decisions.all_for_subject(pid)
    ok = case.case_status == "REVIEW" and len(records) == 0
    print(f"  case_status={case.case_status} (insufficient_funds base_success_rate=0.45 -> REVIEW, not ALLOW)")
    print(f"  DecisionRecords for {pid}: {len(records)} (expected 0)")
    print("PASS" if ok else "FAIL")
    return ok


def test_decision_action_link(actions, record) -> bool:
    print("\n-- 3. Decision -> Action link is real, not just an id that happens to exist --")
    action = actions.get_by_action_id(record.action_id)
    ok = (action is not None and action.action_id == record.action_id
          and action.case_id == record.case_id)
    print(f"  record.action_id={record.action_id[:8] if record.action_id else None}, "
          f"resolved Action.action_id={action.action_id[:8] if action else None}")
    print(f"  case_id matches: {action.case_id == record.case_id if action else False}")
    print("PASS" if ok else "FAIL")
    return ok


def test_historical_replay(events, record, pid) -> bool:
    """The spec's own scoped claim: world_as_of + logic_version +
    policy_version + unchanged entity_matches -> same decision. Rebuilds
    state from the SAME event log at the recorded world_as_of, reusing
    the SAME entity_matches (honest per the spec's named limitation --
    entity resolution is never re-run per as_of cutoff), and confirms a
    completely fresh Recovery call reproduces the stored decision/score/reason
    exactly."""
    print("\n-- 4. Historical replay: fresh recomputation matches the stored DecisionRecord --")
    _fresh(REPLAY_STATE_DB)
    _fresh(REPLAY_GRAPH_DB)
    state = FinancialStateStore(REPLAY_STATE_DB)
    for fn in (reference_ingestion.ingest_merchants, reference_ingestion.ingest_customers,
               reference_ingestion.ingest_devices, reference_ingestion.ingest_instruments):
        fn(state, RAW_DIR, "replay")
    state.commit()
    project(events, state, as_of=record.world_as_of)
    state.close()

    # entity_matches reused as-is from STATE_DB (copy the table) -- per the
    # spec's own finding, entity resolution is never re-run per as_of cutoff
    # anywhere in this system, so an honest replay does the same, rather
    # than silently implying a guarantee (temporal entity resolution) that
    # doesn't exist.
    import sqlite3
    src = sqlite3.connect(str(STATE_DB))
    dst = sqlite3.connect(str(REPLAY_STATE_DB))
    rows = src.execute("SELECT * FROM entity_matches").fetchall()
    cols = [d[0] for d in src.execute("SELECT * FROM entity_matches LIMIT 0").description]
    dst.executemany(f"INSERT INTO entity_matches ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)
    dst.commit()
    src.close()
    dst.close()

    _, replay_graph = build_graph(state_db=REPLAY_STATE_DB, graph_db=REPLAY_GRAPH_DB)
    fresh_verdict = run_recovery_for_payment(replay_graph, pid, investigate=False)

    ok = (fresh_verdict.decision == record.decision
          and fresh_verdict.decision_score == record.decision_score
          and fresh_verdict.reason == record.reason
          and RECOVERY_LOGIC_VERSION == record.logic_version)
    print(f"  stored:  decision={record.decision} score={record.decision_score} reason={record.reason[:60]!r}")
    print(f"  replayed: decision={fresh_verdict.decision} score={fresh_verdict.decision_score} "
          f"reason={fresh_verdict.reason[:60]!r}")
    print(f"  logic_version unchanged since recording: {RECOVERY_LOGIC_VERSION == record.logic_version}")
    print("PASS" if ok else "FAIL")
    return ok


def run() -> bool:
    print("Building event log + one consequential (RETRY) and one non-consequential (REVIEW) decision...")
    events, actions, decisions, graph, retry_pid, review_pid = setup()

    ok1, record = test_consequential_decision_recorded(events, actions, decisions, graph, retry_pid)
    ok2 = test_non_consequential_decision_not_recorded(events, actions, decisions, graph, review_pid)
    ok3 = test_decision_action_link(actions, record) if record else False
    ok4 = test_historical_replay(events, record, retry_pid) if record else False

    results = {
        "consequential_decision_recorded": ok1,
        "non_consequential_decision_not_recorded": ok2,
        "decision_action_link": ok3,
        "historical_replay_matches": ok4,
    }
    print("\n== summary ==")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    passed = all(results.values())
    print(f"\nDECISION PROVENANCE ADVERSARIAL TEST: {'PASS' if passed else 'FAIL'}")
    return passed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(0 if run() else 1)
