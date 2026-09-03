"""
Phase 11 -- Demo assembly. The 5-minute pitch's live demo, run against the
real pipeline -- every line below is a real function call already proven
elsewhere in this repository (see the module docstrings this script
imports from). Nothing here is scripted output; the payment used is picked fresh, by
category, every run (never hardcoded -- IDs are uuid4()-based and not
seed-reproducible, only aggregate statistics are), and every downstream
step is deterministic given that choice.

Five screens, matching PITCH_SCRIPT.md's 1:10-2:40 block exactly:
  1. Financial world       -- payment_journey(), before anything happens
  2. Intelligence          -- Recovery's finding + decision
  3. Policy & Action       -- authorization + real execution
  4. Outcome               -- the gateway's response becomes an event
  5. Re-evaluation         -- a FRESH Recovery call, new process-like state,
                              reaching DO_NOT_RETRY with no special-case code

Then one compact supporting view: a real Risk verdict and a real Controller
verdict on two OTHER real cases, proving this is one shared financial
world, not three disconnected demos.

Run directly: `python -m financial_system.demo`
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path

from financial_system.action.action_store import ActionStore
from financial_system.action.loop import run_action_loop_v2
from financial_system.entity_resolution.runner import run_phase2
from financial_system.events.action_projection import project_action_outcome
from financial_system.events.backfill import backfill
from financial_system.events.store import EventStore
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_graph.queries import format_journey, payment_journey
from financial_system.financial_state.builder import build_financial_state
from financial_system.financial_state.store import FinancialStateStore
from financial_system.orchestrator.orchestrator import process_payment
from financial_system.policy.engine import evaluate
from financial_system.recovery.expected_value import compute_expected_value
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.reconciliation.controller import run_controller_for_settlement
from financial_system.risk.risk_agent import run_risk_for_device

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "financial_system" / "data" / "raw"
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "recovery_labels.csv"
DATA_DIR = REPO_ROOT / "financial_system" / "data"

STATE_DB = DATA_DIR / "financial_state_demo.db"
GRAPH_DB = DATA_DIR / "financial_graph_demo.db"
GRAPH_DB_AFTER = DATA_DIR / "financial_graph_demo_after.db"
EVENTS_DB = DATA_DIR / "events_demo.db"
ACTIONS_DB = DATA_DIR / "actions_demo.db"

# Payment IDs are uuid4()-based (financial_system/data_generator/generate_dataset.py),
# NOT seeded by random.seed() -- every dataset regeneration produces a
# genuinely different set of IDs even at the same seed, only the aggregate
# statistics are seed-reproducible. A hardcoded ID here would go stale the
# next time the dataset is regenerated. Selected fresh, every run, the same
# way every other working script this session does it: the first real
# technical_failure payment whose retry genuinely succeeds, per ground truth.
def _pick_payment_id() -> str:
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return next(r["payment_id"] for r in rows
                if r["failure_reason"] == "technical_failure" and r["retry_would_succeed"] == "True")


def _fresh(path: Path) -> None:
    if path.exists():
        path.unlink()


def _rule(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def setup():
    for p in (STATE_DB, GRAPH_DB, GRAPH_DB_AFTER, EVENTS_DB, ACTIONS_DB):
        _fresh(p)
    events = EventStore(EVENTS_DB)
    backfill(events, RAW_DIR)
    state, _ = build_financial_state(db_path=STATE_DB, raw_dir=RAW_DIR)
    violations = run_phase2(db_path=STATE_DB)[0]
    assert not violations
    _, graph = build_graph(state_db=STATE_DB, graph_db=GRAPH_DB)
    actions = ActionStore(ACTIONS_DB)
    return events, actions, graph


def screen_1_financial_world(graph, payment_id: str) -> None:
    _rule("SCREEN 1 -- THE FINANCIAL WORLD")
    print(format_journey(payment_journey(graph, payment_id)))


def screen_2_intelligence(graph, payment_id: str):
    _rule("SCREEN 2 -- INTELLIGENCE: RECOVERY'S FINDING")
    verdict = run_recovery_for_payment(graph, payment_id, investigate=False)
    print(f"Payment:           {payment_id}")
    print(f"Decision:          {verdict.decision}")
    print(f"Decision score:    {verdict.decision_score}  (category base rate, not a per-instance guess)")
    print(f"Reason:            {verdict.reason}")
    print(f"Evidence:          {verdict.evidence}")
    return verdict


def screen_3_policy_and_action(verdict, events, actions, graph, payment_id: str):
    _rule("SCREEN 3 -- POLICY & ACTION")
    policy_decision = evaluate(verdict, has_conflict=False)
    print(f"Policy outcome:    {policy_decision.outcome}  (rule: {policy_decision.rule_id})")
    print(f"Authorized action: {policy_decision.authorized_action}")

    print("\nExecuting...")
    case = run_action_loop_v2(graph, payment_id, events, actions, investigate=False)
    outcome_events = events.events_for_subject(payment_id, "ActionOutcomeObserved")
    return case, outcome_events


def screen_4_outcome(outcome_events, events, state_path: Path, payment_id: str):
    _rule("SCREEN 4 -- OUTCOME BECOMES A FINANCIAL EVENT")
    outcome = outcome_events[-1]
    print(f"Gateway outcome:   {outcome.payload['verification_result']}")
    print(f"Event recorded:    {outcome.event_type}  at {outcome.occurred_at.isoformat()}")

    state = FinancialStateStore(state_path)
    for e in outcome_events:
        project_action_outcome(e, state)
    row = next(dict(r) for r in state.all_rows("payments") if dict(r)["payment_id"] == payment_id)
    print(f"\nPayment status (projected from the event, not hand-edited): {row['status']}")
    print(f"Failure reason:    {row['failure_reason']}")


def screen_5_reevaluation(payment_id: str):
    _rule("SCREEN 5 -- FRESH RE-EVALUATION")
    print("Building a brand-new graph from the changed state -- no Python object")
    print("carries anything over from Screen 2's call.\n")
    _, fresh_graph = build_graph(state_db=STATE_DB, graph_db=GRAPH_DB_AFTER)
    fresh_verdict = run_recovery_for_payment(fresh_graph, payment_id, investigate=False)
    print(f"Fresh Recovery decision: {fresh_verdict.decision}")
    print(f"Reason:                  {fresh_verdict.reason}")
    return fresh_verdict


def supporting_view(graph):
    _rule("SUPPORTING VIEW -- ONE SHARED FINANCIAL WORLD")
    # Real cross-domain conflict, found fresh via the same detect_conflicts()
    # logic Phase 8's batch run uses (financial_system/orchestrator) -- not a
    # hardcoded payment ID, since IDs are uuid4()-based and not seed-stable
    # across dataset regenerations. This is stronger evidence than three
    # unrelated verdicts: it's two independently-correct agents disagreeing
    # about the SAME real payment.
    #
    # risk_as_of=<this payment's own created_at> -- a temporal-leakage bug
    # found by this project's own hostile audit (Block 5): Risk's device
    # signal, computed over a device's ENTIRE history, could rate a device
    # HIGH-risk using OTHER customers' payments that happened AFTER the
    # payment being decided. Scanning with risk_as_of ensures the conflict
    # shown here is a genuinely contemporaneous disagreement, not a
    # hindsight one -- see financial_system/risk/signals.py.
    state = FinancialStateStore(STATE_DB)
    payment_rows = list(state.all_rows("payments"))
    conflict_case = next(
        (c for c in (
            process_payment(graph, dict(r)["payment_id"], investigate=False,
                             risk_as_of=datetime.fromisoformat(dict(r)["created_at"]))
            for r in payment_rows)
         if c.conflicts),
        None,
    )

    if conflict_case is not None:
        print(f"Payment {conflict_case.subject} -- multiple agents, same real payment, real disagreement:\n")
        if conflict_case.controller_verdict:
            cv = conflict_case.controller_verdict
            print(f"  CONTROLLER: {cv.decision}  ({cv.reason})")
        if conflict_case.risk_verdict:
            rk = conflict_case.risk_verdict
            print(f"  RISK:       {rk.decision}  (score={rk.decision_score:.2f})  ({rk.reason})")
        if conflict_case.recovery_verdict:
            rv = conflict_case.recovery_verdict
            print(f"  RECOVERY:   {rv.decision}  (score={rv.decision_score})  ({rv.reason})")
        print("\n  CONFLICT DETECTED (not silently averaged away):")
        for c in conflict_case.conflicts:
            print(f"  - {c}")

        # Expected-value Recovery decisioning (Phase 5/6): the same real
        # value/fee/cross-domain-risk economics already proven in
        # financial_system/recovery/expected_value.py, evaluated here
        # through the actual Policy engine -- not a separate narrative.
        rv = conflict_case.recovery_verdict
        if rv is not None and rv.proposed_action.startswith("RETRY"):
            ev = compute_expected_value(graph, conflict_case.subject)
            if ev is not None:
                policy_decision = evaluate(rv, has_conflict=True, ev_result=ev)
                print("\n  POLICY")
                print(f"    Recovery proposed {rv.decision} (category base rate {rv.decision_score:.0%})")
                print(f"    Expected utility: Rs.{ev.expected_value:.2f} "
                      f"(value Rs.{ev.value:.2f}, fee Rs.{ev.fee_cost:.2f}, "
                      f"{ev.risk_tier}-risk fraud exposure Rs.{ev.harm_cost:.2f})")
                print(f"    -> {policy_decision.outcome} ({policy_decision.rule_id})")
        return

    # Fallback -- should not trigger against the committed dataset (25 real
    # conflicts confirmed in Phase 8's batch run over the same raw data), but
    # kept so an unrelated dataset regeneration degrades gracefully instead
    # of crashing the demo.
    print("(no cross-domain conflict found in this scan -- showing three independent verdicts instead)")
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    review_pid = next(r for r in rows if r["failure_reason"] == "insufficient_funds")["payment_id"]
    rv = run_recovery_for_payment(graph, review_pid, investigate=False)
    print(f"RECOVERY   {review_pid}: {rv.decision}  (score={rv.decision_score})")
    first_settlement = dict(next(iter(state.all_rows("settlements"))))["settlement_id"]
    cv = run_controller_for_settlement(graph, first_settlement, investigate=False)
    print(f"CONTROLLER {first_settlement}: {cv.decision}")
    for r in graph.all_edges():
        if r.relation != "uses":
            continue
        sharers = graph.edges_to(r.object_id, "uses")
        if len(sharers) >= 2:
            rk = run_risk_for_device(graph, r.object_id, investigate=False)
            print(f"RISK       {r.object_id}: {rk.decision}  (score={rk.decision_score:.2f})")
            break


def run() -> None:
    print("Project Heimdall -- live demo\n")
    events, actions, graph = setup()
    payment_id = _pick_payment_id()

    screen_1_financial_world(graph, payment_id)
    verdict = screen_2_intelligence(graph, payment_id)
    case, outcome_events = screen_3_policy_and_action(verdict, events, actions, graph, payment_id)
    screen_4_outcome(outcome_events, events, STATE_DB, payment_id)
    fresh_verdict = screen_5_reevaluation(payment_id)
    supporting_view(graph)

    _rule("DONE")
    ok = fresh_verdict.decision == "DO_NOT_RETRY"
    print(f"Loop closed correctly: {ok}")
    events.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    run()
