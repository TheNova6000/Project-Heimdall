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

from datetime import datetime

from financial_system.discovery_adapter.investigate import investigate_evidence
from financial_system.discovery_adapter.models import InvestigationRequest, InvestigationResult, InvestigationStatus
from financial_system.financial_graph.repository import GraphRepository
from financial_system.orchestrator.compound_case import CompoundCase, merge
from financial_system.orchestrator.events import agents_for_events, classify_event_types
from financial_system.reconciliation.controller import run_controller_for_settlement
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.risk.risk_agent import run_risk_for_device


def process_payment(graph: GraphRepository, payment_id: str, investigate: bool = False,
                     risk_as_of: datetime | None = None) -> CompoundCase:
    """risk_as_of: opt-in temporal scope for Risk's device-sharing signal
    (Block 5's hostile audit -- Risk's signal is computed over a device's
    entire observed history by default, which leaks future evidence into
    earlier decisions; see financial_system/risk/signals.py). Omitting it
    preserves this function's exact prior behavior -- Phase 8's own proven
    25-conflict full-corpus result is unaffected unless a caller opts in."""
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
                risk_verdict = run_risk_for_device(graph, device_id, investigate=investigate,
                                                    as_of=risk_as_of)

    if "recovery" in invoked:
        recovery_verdict = run_recovery_for_payment(graph, payment_id, investigate=investigate)

    case = merge(payment_id, events, invoked, controller_verdict, risk_verdict, recovery_verdict)

    # Real cross-domain investigation, only when a genuine conflict exists AND
    # the caller opts in -- Recovery's own investigation trigger (unrecognized
    # failure_reason) never fires on this dataset (Block 1: 0/1000 unknown
    # categories); a real cross-domain conflict is where genuine ambiguity
    # actually shows up. Purely explanatory: reuses the same multi-step
    # investigation loop already proven (financial_system/discovery_adapter/
    # investigate.py), asks about the SPECIFIC evidence behind this
    # disagreement, and the result is attached to the case for audit -- it
    # never touches any verdict's decision/decision_score/proposed_action or
    # feeds into the EV/Policy pipeline (the same firewall Controller's own
    # investigation already respects).
    if investigate and case.conflicts and risk_verdict is not None and recovery_verdict is not None:
        question = (
            f"Risk independently flags this payment's device as {risk_verdict.decision} "
            f"(score={risk_verdict.decision_score:.2f}, reason: {risk_verdict.reason}). "
            f"Recovery independently proposes {recovery_verdict.decision} on this payment "
            f"(category base rate {recovery_verdict.decision_score:.0%}, reason: {recovery_verdict.reason}). "
            f"Given the evidence actually connected to this specific payment, is there anything "
            f"that makes retrying it look more or less safe than these two aggregate signals "
            f"already suggest on their own?"
        )
        request = InvestigationRequest(subject_type="Payment", subject_id=payment_id, question_text=question)
        prefilled = InvestigationResult(
            request=request, status=InvestigationStatus.UNEXPLAINED,
            evidence=list(dict.fromkeys(risk_verdict.evidence + recovery_verdict.evidence)),
        )
        case.conflict_investigation = investigate_evidence(request, prefilled, graph)

    return case
