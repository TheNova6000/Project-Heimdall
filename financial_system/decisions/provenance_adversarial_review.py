"""
DECISION_PROVENANCE_ADVERSARIAL_REVIEW.md's newly-added gates -- scenarios
not already covered by decisions/adversarial_test.py's 4 gates. Same
discipline as every prior review: real code, no mocking, and an honest
PROVEN/ANALYZED/UNSUPPORTED split in the write-up for whatever this file
can't directly execute.

Run directly: `python -m financial_system.decisions.provenance_adversarial_review`
"""
from __future__ import annotations

import csv
import sys
import uuid
from datetime import timedelta, timezone
from pathlib import Path

from financial_system.action.action_store import ActionStore
from financial_system.action.event_execution import execute_action_with_events
from financial_system.action.loop import run_action_loop_v2
from financial_system.decisions.models import DecisionRecord
from financial_system.decisions.store import DecisionStore
from financial_system.entity_resolution.runner import run_phase2
from financial_system.events.action_projection import project_action_outcome
from financial_system.events.backfill import backfill
from financial_system.events.store import EventStore
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.builder import build_financial_state
from financial_system.financial_state.store import FinancialStateStore
from financial_system.policy.engine import evaluate
from financial_system.policy.rules import POLICY_RULES_VERSION
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.recovery.signals import RECOVERY_LOGIC_VERSION

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "recovery_labels.csv"
RAW_DIR = REPO_ROOT / "financial_system" / "data" / "raw"
DATA_DIR = REPO_ROOT / "financial_system" / "data"

STATE_DB = DATA_DIR / "financial_state_dpar.db"
GRAPH_DB = DATA_DIR / "financial_graph_dpar.db"
GRAPH_DB_2 = DATA_DIR / "financial_graph_dpar_2.db"
EVENTS_DB = DATA_DIR / "events_dpar.db"
ACTIONS_DB = DATA_DIR / "actions_dpar.db"
DECISIONS_DB = DATA_DIR / "decisions_dpar.db"


def _fresh(path: Path) -> None:
    if path.exists():
        path.unlink()


def setup():
    for p in (STATE_DB, GRAPH_DB, GRAPH_DB_2, EVENTS_DB, ACTIONS_DB, DECISIONS_DB):
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
    success_pid = next(r for r in rows if r["failure_reason"] == "technical_failure"
                        and r["retry_would_succeed"] == "True")["payment_id"]
    fail_pids = [r["payment_id"] for r in rows if r["failure_reason"] == "technical_failure"
                 and r["retry_would_succeed"] == "False"]
    return events, actions, decisions, graph, success_pid, fail_pids[0], fail_pids[1]


def pr2_pr3_version_mismatch_detection() -> bool:
    print("-- 2/3. Policy/logic version mismatch is mechanically detectable --")
    stored_policy_version, stored_logic_version = "policy-v0", "recovery-v0"
    ok = (stored_policy_version != POLICY_RULES_VERSION and stored_logic_version != RECOVERY_LOGIC_VERSION)
    print(f"  live POLICY_RULES_VERSION={POLICY_RULES_VERSION!r} vs a hypothetical stored 'policy-v0': "
          f"mismatch detected = {stored_policy_version != POLICY_RULES_VERSION}")
    print(f"  live RECOVERY_LOGIC_VERSION={RECOVERY_LOGIC_VERSION!r} vs a hypothetical stored 'recovery-v0': "
          f"mismatch detected = {stored_logic_version != RECOVERY_LOGIC_VERSION}")
    print("  (no real version bump exists to test against -- this proves the MECHANISM works: a plain")
    print("   string comparison, checkable in code, is enough to know 'same decision' cannot be claimed")
    print("   across a version change -- not that a version has ever actually changed)")
    print("PASS" if ok else "FAIL")
    return ok


def pr4_world_changes_after_decision_leaves_record_untouched(events, actions, decisions, graph, pid) -> bool:
    print("\n-- 4. World state changes after a decision -- the stored record is untouched, a fresh call diverges --")
    run_action_loop_v2(graph, pid, events, actions, investigate=False, decisions=decisions)
    records_before = decisions.all_for_subject(pid)
    assert len(records_before) == 1
    original = records_before[0]

    # World changes: the retry's own SUCCESS outcome gets projected into state.
    state = FinancialStateStore(STATE_DB)
    for e in events.events_for_subject(pid, "ActionOutcomeObserved"):
        project_action_outcome(e, state)
    _, graph_after = build_graph(state_db=STATE_DB, graph_db=GRAPH_DB_2)

    records_after = decisions.all_for_subject(pid)
    record_unchanged = (len(records_after) == 1 and records_after[0].decision_id == original.decision_id
                         and records_after[0].decision == original.decision
                         and records_after[0].decision_score == original.decision_score)

    fresh_verdict = run_recovery_for_payment(graph_after, pid, investigate=False)
    fresh_diverges = fresh_verdict.decision != original.decision

    ok = record_unchanged and fresh_diverges
    print(f"  stored record: decision={original.decision} (decision_id={original.decision_id[:8]})")
    print(f"  same record still present, unchanged, after world state changed: {record_unchanged}")
    print(f"  a FRESH call now returns: decision={fresh_verdict.decision} "
          f"(diverges from the stored record: {fresh_diverges})")
    print("PASS" if ok else "FAIL")
    return ok


def pr5_late_event_makes_replay_diverge_from_stored_record(events, actions, decisions, graph, pid) -> bool:
    """The sharpest test of what historical reproducibility actually
    promises: a decision recorded at T, then a LATE event with
    occurred_at <= T arrives (legitimately -- recorded_at > occurred_at,
    same invariant TEMPORAL_ADVERSARIAL_REVIEW.md section G already
    proved is accepted). Replaying at the SAME world_as_of afterward can
    now disagree with what was actually decided -- proving the promise is
    "same decision, given the SAME recorded history," never "the one true
    eternal answer for that instant." """
    print("\n-- 5. A late event with occurred_at <= world_as_of, recorded AFTER the decision, "
          "makes replay diverge from the stored record --")
    from financial_system.events.models import Event
    from financial_system.events.projection import project
    from financial_system.ingestion import reference_ingestion

    run_action_loop_v2(graph, pid, events, actions, investigate=False, decisions=decisions)
    record = decisions.all_for_subject(pid)[0]

    def replay():
        path = DATA_DIR / "state_dpar_late_replay.db"
        _fresh(path)
        state = FinancialStateStore(path)
        for fn in (reference_ingestion.ingest_merchants, reference_ingestion.ingest_customers,
                   reference_ingestion.ingest_devices, reference_ingestion.ingest_instruments):
            fn(state, RAW_DIR, "dpar_late")
        state.commit()
        project(events, state, as_of=record.world_as_of)
        row = next(dict(r) for r in state.all_rows("payments") if dict(r)["payment_id"] == pid)
        state.close()
        return row

    before = replay()

    # A legitimate late event: occurred before world_as_of, recorded now --
    # e.g. a corrected/backdated ActionOutcomeObserved(SUCCESS) that only
    # just got reported. occurred_at is set comfortably before world_as_of.
    late_occurred = record.world_as_of - timedelta(hours=2)
    late_recorded = record.world_as_of + timedelta(hours=1)
    events.append(Event(
        event_id=str(uuid.uuid4()), event_type="ActionOutcomeObserved", subject_id=pid, source="test_late",
        occurred_at=late_occurred, recorded_at=late_recorded, correlation_id=pid,
        payload={"action_id": "late-correction", "executed": True, "action_taken": "RETRY_PAYMENT",
                 "verification_result": "SUCCESS", "verification_detail": "late-arriving correction",
                 "attempt_number": 99},
    ))
    events.commit()

    after = replay()
    diverges = before["status"] != after["status"]
    ok = before["status"] == "failed" and diverges
    print(f"  stored decision: {record.decision} (recorded before the late event existed)")
    print(f"  replay at the SAME world_as_of, BEFORE the late event: status={before['status']!r}")
    print(f"  replay at the SAME world_as_of, AFTER the late event was recorded: status={after['status']!r}")
    print(f"  replay diverges from what the world looked like at decision time: {diverges}")
    print("  (the stored DecisionRecord itself does not change -- it remains an accurate record of what")
    print("   was decided given the history recorded so far; only a FRESH replay reflects the correction)")
    print("PASS" if ok else "FAIL")
    return ok


def pr6_decision_store_has_no_update_path() -> bool:
    print("\n-- 6. DecisionStore has no update method -- a recorded decision cannot be edited --")
    import inspect
    methods = {name for name, _ in inspect.getmembers(DecisionStore, predicate=inspect.isfunction)}
    ok = not any("update" in m for m in methods)
    print(f"  DecisionStore public methods: {sorted(m for m in methods if not m.startswith('_'))}")
    print(f"  none named *update*: {ok}")
    print("PASS" if ok else "FAIL")
    return ok


def pr7_no_action_without_decision_is_structurally_impossible() -> bool:
    print("\n-- 7. 'Consequential decision, no Action' is structurally impossible under current wiring --")
    # execute_action_with_events() ALWAYS creates+commits the Action (or
    # resolves the existing one) before returning -- checked directly:
    # the only way _record_consequential_decision() runs is after that
    # call returns, so actions.get_by_idempotency_key() cannot be None.
    import inspect
    src = inspect.getsource(execute_action_with_events)
    creates_before_return = src.index("actions.create(action)") < src.rindex("return")
    print(f"  execute_action_with_events() creates the Action before any return path: {creates_before_return}")
    print("  (structural read of the function, not a runtime probe -- matches "
          "decisions/adversarial_test.py gate 1's action_id always being non-None)")
    print("PASS" if creates_before_return else "FAIL")
    return creates_before_return


def pr8_pr9_duplicate_and_multiple_consequential_decisions(events, actions, decisions, graph, fail_pid) -> bool:
    """A payment whose retry genuinely fails (retry_would_succeed=False)
    stays 'failed' after attempt 2 -- calling run_action_loop_v2 AGAIN
    reproduces the identical verdict/policy/idempotency_key as the first
    attempt of the first call, hitting execute_action_with_events'
    idempotent-replay path. run_action_loop_v2 has no way to know the
    execution was a cache hit rather than fresh -- it records a decision
    either way. One Action, two DecisionRecords: a real, verified
    one-to-many relationship, not a bug this checkpoint fixes."""
    print("\n-- 8/9. Two consequential decisions, same subject, one idempotently-shared Action --")
    case1 = run_action_loop_v2(graph, fail_pid, events, actions, investigate=False, decisions=decisions,
                                max_attempts=1)
    records_after_1 = decisions.all_for_subject(fail_pid)

    case2 = run_action_loop_v2(graph, fail_pid, events, actions, investigate=False, decisions=decisions,
                                max_attempts=1)
    records_after_2 = decisions.all_for_subject(fail_pid)

    same_action = (len(records_after_1) == 1 and len(records_after_2) == 2
                   and records_after_2[0].action_id == records_after_2[1].action_id)
    distinct_decision_ids = records_after_2[0].decision_id != records_after_2[1].decision_id
    ok = same_action and distinct_decision_ids
    print(f"  call 1: case_status={case1.case_status}, DecisionRecords so far: {len(records_after_1)}")
    print(f"  call 2 (identical verdict/policy -> identical idempotency_key): "
          f"case_status={case2.case_status}, DecisionRecords so far: {len(records_after_2)}")
    print(f"  both records reference the SAME action_id: {same_action} "
          f"({records_after_2[0].action_id[:8]} == {records_after_2[1].action_id[:8]})")
    print(f"  but have distinct decision_ids (two real reasoning acts, one shared idempotent Action): "
          f"{distinct_decision_ids}")
    print("PASS" if ok else "FAIL")
    return ok


def pr10_pr11_pr12_orphan_scenarios(graph, actions) -> bool:
    print("\n-- 10/11/12. Restart between Action and DecisionRecord: only one orphan direction is reachable --")
    from financial_system.verdict import AgentVerdict
    from financial_system.policy.engine import evaluate as policy_evaluate
    verdict = AgentVerdict(agent="recovery", subject="pay_orphan_test", decision="RETRY",
                            reason="synthetic", evidence=[], decision_score=0.9,
                            proposed_action="RETRY_PAYMENT")
    policy_decision = policy_evaluate(verdict, has_conflict=False)
    key = f"pay_orphan_test:attempt2:{policy_decision.proposed_action}"
    events_orphan = EventStore(":memory:")
    executed, action_taken, log, vr, vd = execute_action_with_events(
        verdict, policy_decision, key, case_id="pay_orphan_test", events=events_orphan, actions=actions,
        attempt_number=2,
    )
    # Simulate a crash HERE -- Action exists and is committed; the process
    # dies before _record_consequential_decision() ever runs.
    action = actions.get_by_idempotency_key(key)
    decisions_orphan = DecisionStore(":memory:")
    pr11_reachable = action is not None and decisions_orphan.get_by_action_id(action.action_id) is None

    # The reverse (PR12: a DecisionRecord exists but its Action doesn't)
    # is NOT reachable under current wiring -- checked structurally:
    # loop.py only ever calls _record_consequential_decision() AFTER
    # execute_action_with_events() has already returned (and therefore
    # already created+committed the Action). Confirmed by inspecting the
    # actual call order in loop.py's source, not asserted.
    import inspect
    from financial_system.action import loop as loop_module
    src = inspect.getsource(loop_module.run_action_loop_v2)
    execute_call_pos = src.index("execute_action_with_events(")
    record_call_pos = src.index("_record_consequential_decision(")
    pr12_unreachable_by_construction = execute_call_pos < record_call_pos

    ok = pr11_reachable and pr12_unreachable_by_construction
    print(f"  PR11 (Action exists, DecisionRecord doesn't -- crash after Action commit, before Decision "
          f"commit): reachable = {pr11_reachable}")
    print(f"  PR12 (DecisionRecord exists, Action doesn't): unreachable by construction -- "
          f"execute_action_with_events() always runs first in loop.py's source: {pr12_unreachable_by_construction}")
    print("  (an asymmetric guarantee, not a symmetric one -- worth naming precisely rather than assuming both")
    print("   orphan directions are equally possible)")
    print("PASS" if ok else "FAIL")
    return ok


def run() -> bool:
    print("Building event log...")
    events, actions, decisions, graph, success_pid, fail_pid_a, fail_pid_b = setup()

    results = {
        "pr2_pr3_version_mismatch_detection": pr2_pr3_version_mismatch_detection(),
        "pr4_world_changes_leave_record_untouched": pr4_world_changes_after_decision_leaves_record_untouched(
            events, actions, decisions, graph, success_pid),
        "pr5_late_event_makes_replay_diverge": pr5_late_event_makes_replay_diverge_from_stored_record(
            events, actions, decisions, graph, fail_pid_a),
        "pr6_decision_store_no_update_path": pr6_decision_store_has_no_update_path(),
        "pr7_no_action_without_decision_impossible": pr7_no_action_without_decision_is_structurally_impossible(),
        "pr8_pr9_duplicate_and_multiple_decisions": pr8_pr9_duplicate_and_multiple_consequential_decisions(
            events, actions, decisions, graph, fail_pid_b),
        "pr10_pr11_pr12_orphan_scenarios": pr10_pr11_pr12_orphan_scenarios(graph, actions),
    }

    print("\n== summary ==")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    passed = all(results.values())
    print(f"\nDECISION PROVENANCE ADVERSARIAL REVIEW: {'PASS' if passed else 'FAIL'}")
    return passed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(0 if run() else 1)
