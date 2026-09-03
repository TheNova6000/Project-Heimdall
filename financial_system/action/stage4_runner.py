"""
Stage 4 acceptance tests (five gates, this stage's own design turn):

1. Projection boundary -- ActionRequested/ActionExecutionStarted cannot
   change state; only ActionOutcomeObserved can.
2. Persistence -- close and reopen the state store (simulating a process
   restart); the transition must still be there, read fresh, not from
   anything held in memory.
3. Re-entry -- the new observation must reach the orchestrator: rebuild the
   graph from the mutated state and confirm classify_event_types() no
   longer reports PAYMENT_FAILED for the recovered payment.
4. Behavioral preservation -- inherited from Stage 3's own 0/160 result
   (not re-run in full here; nothing in Stage 4 touches run_action_loop or
   run_action_loop_v2's own logic, only adds a projector downstream of it).
5. No phantom facts -- neither "no ActionOutcomeObserved exists" nor "an
   ActionOutcomeObserved(FAILURE) exists" may produce a state transition.

Everything here runs against an ISOLATED copy of financial_state
(financial_state_stage4.db) -- never the shared financial_state.db every
other phase's tests depend on.

Run directly: `python -m financial_system.action.stage4_runner`
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from financial_system.action.action_store import ActionStore
from financial_system.action.loop import run_action_loop_v2
from financial_system.entity_resolution.runner import run_phase2
from financial_system.events.action_projection import project_action_outcome
from financial_system.events.store import EventStore
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.builder import build_financial_state
from financial_system.financial_state.store import FinancialStateStore
from financial_system.orchestrator.events import classify_event_types
from financial_system.recovery.recovery_agent import run_recovery_for_payment

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "recovery_labels.csv"
RAW_DIR = REPO_ROOT / "financial_system" / "data" / "raw"

STATE_DB = REPO_ROOT / "financial_system" / "data" / "financial_state_stage4.db"
GRAPH_DB = REPO_ROOT / "financial_system" / "data" / "financial_graph_stage4.db"
GRAPH_DB_2 = REPO_ROOT / "financial_system" / "data" / "financial_graph_stage4_after.db"
EVENTS_DB = REPO_ROOT / "financial_system" / "data" / "events_stage4.db"
ACTIONS_DB = REPO_ROOT / "financial_system" / "data" / "actions_stage4.db"


def load_labels() -> list[dict]:
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def setup():
    """Isolated state + graph, built once, entity resolution run once
    (payment-status changes never affect settlement<->bank matches, so it
    doesn't need re-running after the mutation)."""
    state, _ = build_financial_state(db_path=STATE_DB, raw_dir=RAW_DIR)
    violations = run_phase2(db_path=STATE_DB)[0]
    assert not violations, f"unexpected reference-key violations: {violations}"
    _, graph = build_graph(state_db=STATE_DB, graph_db=GRAPH_DB)

    if EVENTS_DB.exists():
        EVENTS_DB.unlink()
    if ACTIONS_DB.exists():
        ACTIONS_DB.unlink()
    events, actions = EventStore(EVENTS_DB), ActionStore(ACTIONS_DB)
    return graph, events, actions


def run_gate1(graph, events, actions) -> tuple[bool, str, str]:
    """Returns (ok, success_payment_id, failure_payment_id) -- the two
    payments used by later gates, chosen here so setup is shared."""
    print("-- Gate 1: projection boundary --")
    labels = load_labels()
    success_case = next(r for r in labels if r["failure_reason"] == "technical_failure"
                         and r["retry_would_succeed"] == "True")
    failure_case = next(r for r in labels if r["failure_reason"] == "technical_failure"
                         and r["retry_would_succeed"] == "False")
    success_pid, failure_pid = success_case["payment_id"], failure_case["payment_id"]

    state = FinancialStateStore(STATE_DB)
    before = dict(state.all_rows("payments")[0])  # just to confirm the store is readable
    status_before = next(dict(r)["status"] for r in state.all_rows("payments") if dict(r)["payment_id"] == success_pid)

    run_action_loop_v2(graph, success_pid, events, actions, investigate=False)

    requested = events.events_for_subject(success_pid, "ActionRequested")
    started = events.events_for_subject(success_pid, "ActionExecutionStarted")
    outcome = events.events_for_subject(success_pid, "ActionOutcomeObserved")

    no_mutation_from_requested = all(not project_action_outcome(e, state) for e in requested)
    no_mutation_from_started = all(not project_action_outcome(e, state) for e in started)
    status_still_before = next(dict(r)["status"] for r in state.all_rows("payments")
                                if dict(r)["payment_id"] == success_pid) == status_before

    mutated = any(project_action_outcome(e, state) for e in outcome)
    status_after = next(dict(r)["status"] for r in state.all_rows("payments")
                         if dict(r)["payment_id"] == success_pid)

    ok = (no_mutation_from_requested and no_mutation_from_started and status_still_before
          and mutated and status_after == "success")
    print(f"  ActionRequested/Started events: {len(requested)}/{len(started)} -- neither mutated state "
          f"[{'OK' if no_mutation_from_requested and no_mutation_from_started else 'FAIL'}]")
    print(f"  status before any outcome projected: {status_before} (unchanged through Requested/Started)")
    print(f"  ActionOutcomeObserved projected -> status now: {status_after} [{'OK' if mutated else 'FAIL'}]")
    print("GATE 1: PASS" if ok else "GATE 1: FAIL")
    return ok, success_pid, failure_pid


def run_gate2(success_pid: str) -> bool:
    print("\n-- Gate 2: persistence across a simulated restart --")
    # "Restart": open a brand-new connection to the same db file, nothing
    # carried over from the process that made the change.
    fresh = FinancialStateStore(STATE_DB)
    status = next(dict(r)["status"] for r in fresh.all_rows("payments") if dict(r)["payment_id"] == success_pid)
    ok = status == "success"
    print(f"  status read from a fresh connection: {status} [{'OK' if ok else 'FAIL'}]")
    print("GATE 2: PASS" if ok else "GATE 2: FAIL")
    return ok


def run_gate3(success_pid: str) -> bool:
    print("\n-- Gate 3: re-entry to the orchestrator --")
    _, graph_after = build_graph(state_db=STATE_DB, graph_db=GRAPH_DB_2)
    events_now = classify_event_types(graph_after, success_pid)
    no_longer_failed = "PAYMENT_FAILED" not in events_now

    verdict = run_recovery_for_payment(graph_after, success_pid, investigate=False)
    no_longer_retry_candidate = verdict.decision != "RETRY"

    ok = no_longer_failed and no_longer_retry_candidate
    print(f"  classify_event_types() after outcome: {events_now} [{'OK' if no_longer_failed else 'FAIL'}]")
    print(f"  Recovery's fresh verdict: decision={verdict.decision} reason={verdict.reason[:70]} "
          f"[{'OK' if no_longer_retry_candidate else 'FAIL'}]")
    print("GATE 3: PASS" if ok else "GATE 3: FAIL")
    return ok


def run_gate5(graph, events, actions, failure_pid: str) -> bool:
    print("\n-- Gate 5: no phantom facts --")
    state = FinancialStateStore(STATE_DB)
    status_before = next(dict(r)["status"] for r in state.all_rows("payments")
                          if dict(r)["payment_id"] == failure_pid)

    # No event at all yet for this payment's action -- nothing to project.
    no_event_mutation = not any(
        project_action_outcome(e, state) for e in events.events_for_subject(failure_pid))

    # Now actually run it -- retry_would_succeed=False, so the outcome IS
    # FAILURE. Confirm an observed FAILURE also produces no transition.
    run_action_loop_v2(graph, failure_pid, events, actions, investigate=False)
    outcome_events = events.events_for_subject(failure_pid, "ActionOutcomeObserved")
    failure_mutation = any(project_action_outcome(e, state) for e in outcome_events)

    status_after = next(dict(r)["status"] for r in state.all_rows("payments")
                         if dict(r)["payment_id"] == failure_pid)

    ok = no_event_mutation and not failure_mutation and status_after == status_before == "failed"
    print(f"  before any event exists: mutation attempted={not no_event_mutation} [expected False]")
    print(f"  ActionOutcomeObserved(FAILURE) events: {len(outcome_events)}, "
          f"any produced a mutation={failure_mutation} [expected False]")
    print(f"  status unchanged: {status_before} -> {status_after} [{'OK' if ok else 'FAIL'}]")
    print("GATE 5: PASS" if ok else "GATE 5: FAIL")
    return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Setting up isolated Stage 4 state/graph...")
    graph, events, actions = setup()

    gate1, success_pid, failure_pid = run_gate1(graph, events, actions)
    gate2 = run_gate2(success_pid) if gate1 else False
    gate3 = run_gate3(success_pid) if gate2 else False
    gate5 = run_gate5(graph, events, actions, failure_pid)
    print("\n-- Gate 4: behavioral preservation -- inherited from Stage 3's own "
          "0/160 result; nothing in Stage 4 modifies run_action_loop[_v2]'s logic, "
          "only adds a projector strictly downstream of it.")

    passed = gate1 and gate2 and gate3 and gate5
    print(f"\nSTAGE 4: {'PASS' if passed else 'FAIL'}")
    sys.exit(0 if passed else 1)
