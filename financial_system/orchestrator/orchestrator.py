"""
Phase 8: Financial Orchestrator. Coordination only, deterministic, no LLM,
no fourth intelligence model of its own (ARCHITECTURE.md's own warning: the
orchestrator's job is coordination, not becoming a mysterious fourth brain).

    Payment
       |
    classify_event_types()  (events.py)
       |
    agents_for_events()  -- which of Controller/Risk/Recovery actually apply
       |
    run each invoked agent, independently, on ITS OWN subject:
       controller -> the payment's settlement (if any)
       risk       -> the payment's device (if it has sharers)
       recovery   -> the payment itself (if failed)
       |
    merge()  (compound_case.py) -- verdicts kept whole, never flattened
       |
    CompoundCase
"""
from __future__ import annotations

from financial_system.financial_graph.repository import GraphRepository
from financial_system.orchestrator.compound_case import CompoundCase, merge
from financial_system.orchestrator.events import agents_for_events, classify_event_types
from financial_system.reconciliation.controller import run_controller_for_settlement
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.risk.risk_agent import run_risk_for_device


def process_payment(graph: GraphRepository, payment_id: str, investigate: bool = False) -> CompoundCase:
    events = classify_event_types(graph, payment_id)
    invoked = agents_for_events(events)

    controller_verdict = risk_verdict = recovery_verdict = None

    if "controller" in invoked:
        settlement_edges = graph.edges_from(payment_id, "settles_into")
        if settlement_edges:
            controller_verdict = run_controller_for_settlement(
                graph, settlement_edges[0].object_id, investigate=investigate)

    if "risk" in invoked:
        device_edges = graph.edges_from(payment_id, "used_device")
        if device_edges:
            device_id = device_edges[0].object_id
            sharer_edges = graph.edges_to(device_id, "uses")
            if len(sharer_edges) >= 2:   # signals.py's own definition of "carries a network signal"
                risk_verdict = run_risk_for_device(graph, device_id, investigate=investigate)

    if "recovery" in invoked:
        recovery_verdict = run_recovery_for_payment(graph, payment_id, investigate=investigate)

    return merge(payment_id, events, invoked, controller_verdict, risk_verdict, recovery_verdict)
