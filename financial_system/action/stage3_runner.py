"""
Stage 3 acceptance tests (MIGRATION_DESIGN.md §9, plus the three mandatory
idempotency gates from this stage's own design turn):

1. Behavioral preservation: run_action_loop() (Phase 10, untouched) and
   run_action_loop_v2() (Stage 3, event-emitting) must produce IDENTICAL
   case_status and attempt counts across all 160 failed payments.
2. Gate A -- same request twice -> exactly one logical execution.
3. Gate B -- same key, different parameters -> rejected, no second execution.
4. Gate C -- a simulated crash mid-execution is recovered from the event
   log, never blindly re-executed. Two sub-cases: C1 (truly stuck, no
   outcome anywhere -- refuse safely) and C2 (the outcome WAS recorded
   before the crash, just Action's own status wasn't updated -- recover it).

Run directly: `python -m financial_system.action.stage3_runner`
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

from financial_system.action.action_store import ActionStore
from financial_system.action.event_execution import execute_action_with_events
from financial_system.action.loop import run_action_loop, run_action_loop_v2
from financial_system.action.models import Action
from financial_system.events.models import Event
from financial_system.events.store import EventStore
from financial_system.financial_graph.builder import build_graph
from financial_system.policy.engine import evaluate
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.verdict import AgentVerdict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "recovery_labels.csv"
EVENTS_DB = REPO_ROOT / "financial_system" / "data" / "events_stage3.db"
ACTIONS_DB = REPO_ROOT / "financial_system" / "data" / "actions_stage3.db"


def load_labels() -> list[dict]:
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_behavioral_preservation(graph) -> bool:
    print("-- Behavioral preservation: run_action_loop vs. run_action_loop_v2 --")
    if EVENTS_DB.exists():
        EVENTS_DB.unlink()
    if ACTIONS_DB.exists():
        ACTIONS_DB.unlink()
    events = EventStore(EVENTS_DB)
    actions = ActionStore(ACTIONS_DB)

    labels = load_labels()
    mismatches = []
    for i, row in enumerate(labels, 1):
        pid = row["payment_id"]
        original = run_action_loop(graph, pid, investigate=False)
        v2 = run_action_loop_v2(graph, pid, events, actions, investigate=False)
        if original.case_status != v2.case_status or len(original.attempts) != len(v2.attempts):
            mismatches.append((pid, original.case_status, len(original.attempts),
                                v2.case_status, len(v2.attempts)))
        if i % 40 == 0 or i == len(labels):
            print(f"  [{i}/{len(labels)}]")

    ok = not mismatches
    print(f"Mismatches: {len(mismatches)}/{len(labels)}")
    for m in mismatches[:5]:
        print(f"  {m}")
    print(f"Events recorded: {events.count()}")
    print("BEHAVIORAL PRESERVATION: PASS" if ok else "BEHAVIORAL PRESERVATION: FAIL")
    return ok


def _sample_verdict_and_policy(graph):
    """A real technical_failure payment -- RETRY, decision_score=.85, clears
    R3's ALLOW threshold -- so Gates A/B/C exercise a genuine execution path."""
    labels = load_labels()
    row = next(r for r in labels if r["failure_reason"] == "technical_failure")
    verdict = run_recovery_for_payment(graph, row["payment_id"], investigate=False)
    policy_decision = evaluate(verdict, has_conflict=False)
    return row["payment_id"], verdict, policy_decision


def run_gate_a(graph) -> bool:
    print("\n-- Gate A: same request twice -> exactly one execution --")
    events, actions = EventStore(":memory:"), ActionStore(":memory:")
    pid, verdict, policy = _sample_verdict_and_policy(graph)
    key = f"gateA:{pid}"

    r1 = execute_action_with_events(verdict, policy, key, pid, events, actions)
    r2 = execute_action_with_events(verdict, policy, key, pid, events, actions)

    same_result = r1[:3] == r2[:3]  # (executed, action_taken, log) -- log differs on replay (says so), check the rest
    same_outcome = r1[0] == r2[0] and r1[1] == r2[1]
    outcome_events = events.all_events("ActionOutcomeObserved")
    one_execution = len(outcome_events) == 1
    replayed = "IDEMPOTENT REPLAY" in r2[2]

    ok = same_outcome and one_execution and replayed
    print(f"  first call:  executed={r1[0]} action={r1[1]} log={r1[2][:60]}")
    print(f"  second call: executed={r2[0]} action={r2[1]} log={r2[2][:60]}")
    print(f"  ActionOutcomeObserved events recorded: {len(outcome_events)} (expected 1)")
    print("GATE A: PASS" if ok else "GATE A: FAIL")
    return ok


def run_gate_b(graph) -> bool:
    print("\n-- Gate B: same key, different parameters -> rejected --")
    events, actions = EventStore(":memory:"), ActionStore(":memory:")
    pid, verdict, policy = _sample_verdict_and_policy(graph)
    key = f"gateB:{pid}"

    r1 = execute_action_with_events(verdict, policy, key, pid, events, actions)

    different_policy = policy.model_copy(update={"proposed_action": "RETRY_ALT_METHOD"})
    r2 = execute_action_with_events(verdict, different_policy, key, pid, events, actions)

    ok = r1[0] is True and r2[1] == "REJECTED" and not r2[0]
    outcome_events = events.all_events("ActionOutcomeObserved")
    print(f"  first call (original params):  executed={r1[0]} action={r1[1]}")
    print(f"  second call (different params): executed={r2[0]} action={r2[1]} log={r2[2][:80]}")
    print(f"  ActionOutcomeObserved events recorded: {len(outcome_events)} (expected 1, not 2)")
    ok = ok and len(outcome_events) == 1
    print("GATE B: PASS" if ok else "GATE B: FAIL")
    return ok


def run_gate_c(graph) -> bool:
    print("\n-- Gate C: simulated crash mid-execution --")
    pid, verdict, policy = _sample_verdict_and_policy(graph)
    request_signature = {"agent": verdict.agent, "subject": verdict.subject, "decision": verdict.decision,
                          "proposed_action": policy.proposed_action, "policy_outcome": policy.outcome}
    now = datetime.now(timezone.utc)

    # C1: truly stuck -- ActionRequested + ActionExecutionStarted recorded, no
    # outcome anywhere. Must refuse to blindly re-execute.
    events1, actions1 = EventStore(":memory:"), ActionStore(":memory:")
    key1 = f"gateC1:{pid}"
    action1 = Action(action_id="stuck-action-1", idempotency_key=key1, case_id=pid, subject_id=pid,
                      action_type=policy.proposed_action, proposed_by=verdict.agent,
                      authorized_by=policy.rule_id, preconditions=request_signature,
                      created_at=now, execution_status="STARTED", execution_started_at=now)
    actions1.create(action1)
    actions1.commit()
    events1.append(Event(event_id="ev-req-1", event_type="ActionRequested", subject_id=pid,
                          source="policy_engine", occurred_at=now, recorded_at=now,
                          payload={"action_id": "stuck-action-1", **request_signature}, correlation_id=pid))
    events1.append(Event(event_id="ev-start-1", event_type="ActionExecutionStarted", subject_id=pid,
                          source="action_executor", occurred_at=now, recorded_at=now,
                          payload={"action_id": "stuck-action-1"}, correlation_id=pid,
                          causation_id="ev-req-1"))
    events1.commit()

    r_c1 = execute_action_with_events(verdict, policy, key1, pid, events1, actions1)
    c1_ok = (not r_c1[0]) and "already in-flight" in r_c1[2]
    c1_no_duplicate = len(events1.events_for_subject(pid, "ActionRequested")) == 1
    print(f"  C1 (no outcome recorded): executed={r_c1[0]} log={r_c1[2][:70]}")
    print(f"  C1 no duplicate ActionRequested: {c1_no_duplicate}")

    # C2: the outcome WAS recorded before the crash, just Action's own status
    # was never advanced. Must recover it, not re-execute.
    events2, actions2 = EventStore(":memory:"), ActionStore(":memory:")
    key2 = f"gateC2:{pid}"
    action2 = Action(action_id="stuck-action-2", idempotency_key=key2, case_id=pid, subject_id=pid,
                      action_type=policy.proposed_action, proposed_by=verdict.agent,
                      authorized_by=policy.rule_id, preconditions=request_signature,
                      created_at=now, execution_status="STARTED", execution_started_at=now)
    actions2.create(action2)
    actions2.commit()
    events2.append(Event(event_id="ev-req-2", event_type="ActionRequested", subject_id=pid,
                          source="policy_engine", occurred_at=now, recorded_at=now,
                          payload={"action_id": "stuck-action-2", **request_signature}, correlation_id=pid))
    events2.append(Event(event_id="ev-start-2", event_type="ActionExecutionStarted", subject_id=pid,
                          source="action_executor", occurred_at=now, recorded_at=now,
                          payload={"action_id": "stuck-action-2"}, correlation_id=pid,
                          causation_id="ev-req-2"))
    events2.append(Event(event_id="ev-outcome-2", event_type="ActionOutcomeObserved", subject_id=pid,
                          source="gateway_simulator", occurred_at=now, recorded_at=now,
                          payload={"action_id": "stuck-action-2", "executed": True,
                                   "action_taken": policy.proposed_action,
                                   "verification_result": "SUCCESS", "verification_detail": "pre-crash outcome"},
                          correlation_id=pid, causation_id="ev-start-2"))
    events2.commit()

    r_c2 = execute_action_with_events(verdict, policy, key2, pid, events2, actions2)
    c2_ok = r_c2[0] is True and "RECOVERED" in r_c2[2] and r_c2[3] == "SUCCESS"
    c2_no_duplicate = len(events2.events_for_subject(pid, "ActionRequested")) == 1
    print(f"  C2 (outcome pre-recorded): executed={r_c2[0]} log={r_c2[2][:70]} verification={r_c2[3]}")
    print(f"  C2 no duplicate ActionRequested: {c2_no_duplicate}")

    ok = c1_ok and c1_no_duplicate and c2_ok and c2_no_duplicate
    print("GATE C: PASS" if ok else "GATE C: FAIL")
    return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Building graph...")
    state, graph = build_graph()

    behavioral = run_behavioral_preservation(graph)
    gate_a = run_gate_a(graph)
    gate_b = run_gate_b(graph)
    gate_c = run_gate_c(graph)

    passed = behavioral and gate_a and gate_b and gate_c
    print(f"\nSTAGE 3: {'PASS' if passed else 'FAIL'}")
    sys.exit(0 if passed else 1)
