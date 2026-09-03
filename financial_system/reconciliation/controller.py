"""
Phase 5: Controller.

Controller determines what happened (via reconcile_settlement(), zero LLM)
and what to do about it. Discovery.AI is invoked only when the reason
genuinely needs investigating -- never for a settlement that already
reconciles cleanly, never re-run for one Controller has already resolved
itself. This is the boundary to protect: Discovery.AI answers "what evidence
explains this," never "what should we do with the money" -- enforced
structurally here, not just by convention: only `decision`/`proposed_action`
(both Controller's own) drive the outcome, and `investigation_confidence`
is carried on the verdict for audit only, never read to decide anything.

    Settlement -> reconcile_settlement() -> "what is wrong?"
                                                  |
                     +----------------------------+----------------------------+
                     |                |                    |                  |
              no discrepancy   explainable            ambiguous          unexplained
                  PASS       RESOLVE / ADJUST     REVIEW / MANUAL     INVESTIGATE
                                                                    (Discovery.AI called;
                                                                     decision stays
                                                                     INVESTIGATE --
                                                                     narrative is
                                                                     supporting context,
                                                                     not a money decision)
"""
from __future__ import annotations

from financial_system.discovery_adapter.investigate import investigate_evidence
from financial_system.discovery_adapter.models import InvestigationRequest, InvestigationResult, InvestigationStatus
from financial_system.financial_graph.repository import GraphRepository
from financial_system.reconciliation.deterministic import ReconciliationFact, reconcile_settlement
from financial_system.verdict import AgentVerdict


def _to_verdict(fact: ReconciliationFact, investigation: InvestigationResult | None) -> AgentVerdict:
    if fact.status == "EXPLAINED" and not fact.had_raw_discrepancy:
        decision, action, score = "PASS", "NONE", 1.0
    elif fact.status == "EXPLAINED":  # had a real gap, duplicate detection closed it
        decision, action, score = "RESOLVE", "ADJUST", 0.95
    elif fact.status == "PARTIALLY_EXPLAINED":
        decision, action, score = "REVIEW", "MANUAL_REVIEW", 0.5
    else:  # UNEXPLAINED
        decision, action, score = "INVESTIGATE", "ESCALATE_WITH_INVESTIGATION", 0.0

    reason = fact.note or (
        f"expected={fact.expected_amount} actual={fact.actual_amount} "
        f"unexplained={fact.unexplained_amount} duplicate_adjustment={fact.duplicate_adjustment}"
    )
    investigation_confidence = None
    investigation_id = None
    if investigation is not None and investigation.executed_4b:
        investigation_id = fact.settlement_id
        investigation_confidence = investigation.investigation_confidence
        if investigation.narrative:
            reason = investigation.narrative
        if investigation.status.value != fact.status:
            # Discovery.AI's own read of the same case never changes Controller's
            # decision -- log the disagreement, don't act on it.
            reason += f" [Discovery.AI's own classification: {investigation.status.value}]"

    return AgentVerdict(
        agent="controller", subject=fact.settlement_id, decision=decision, reason=reason,
        evidence=fact.evidence, decision_score=score, investigation_confidence=investigation_confidence,
        proposed_action=action, investigation_id=investigation_id,
        metrics={
            "expected": float(fact.expected_amount) if fact.expected_amount is not None else 0.0,
            "actual": float(fact.actual_amount) if fact.actual_amount is not None else 0.0,
            "unexplained": float(fact.unexplained_amount) if fact.unexplained_amount is not None else 0.0,
        },
        affected_entities=[fact.settlement_id],
    )


def run_controller_for_settlement(graph: GraphRepository, settlement_id: str,
                                   investigate: bool = True) -> AgentVerdict:
    fact = reconcile_settlement(graph, settlement_id)

    investigation = None
    if fact.status == "UNEXPLAINED" and investigate and fact.expected_amount is not None:
        request = InvestigationRequest(
            subject_type="Settlement", subject_id=settlement_id,
            question_text=f"Why does settlement {settlement_id}'s recorded net amount "
                          f"differ from what the bank actually deposited?",
        )
        prefilled = InvestigationResult(
            request=request, status=InvestigationStatus.UNEXPLAINED,
            expected_amount=str(fact.expected_amount),
            actual_amount=str(fact.actual_amount) if fact.actual_amount is not None else None,
            unexplained_amount=str(fact.unexplained_amount) if fact.unexplained_amount is not None else None,
            facts=fact.facts, evidence=fact.evidence,
        )
        investigation = investigate_evidence(request, prefilled, graph)

    return _to_verdict(fact, investigation)
