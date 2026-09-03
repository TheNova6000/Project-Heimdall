"""
Phase 7: Recovery agent. Same boundary as Controller/Risk: deterministic
signals (recovery/signals.py) decide the action; Discovery.AI is only asked
to investigate a genuinely ambiguous case (unrecognized failure_reason),
never to decide whether to retry.

    Failed payment
         |
    compute_recovery_signals()
         |
    has_alternate_success? --YES--> DO_NOT_RETRY (avoid a duplicate charge)
         | NO
    known category?  --NO--> INVESTIGATE (Discovery.AI, if enabled)
         | YES
    recoverable category?
       NO  -> ESCALATE / default_action (MANUAL_REVIEW, REQUEST_CUSTOMER_ACTION)
       YES -> RETRY / default_action, decision_score = category's own
              base_success_rate -- never a per-instance prediction. Whether
              THIS specific retry actually succeeds isn't decidable in
              advance from anything in this system; that's what Phase 10
              Verification finds out after the fact, not Recovery's job here.
"""
from __future__ import annotations

from financial_system.discovery_adapter.investigate import investigate_evidence
from financial_system.discovery_adapter.models import InvestigationRequest, InvestigationResult, InvestigationStatus
from financial_system.financial_graph.repository import GraphRepository
from financial_system.recovery.signals import RecoverySignals, compute_recovery_signals
from financial_system.verdict import AgentVerdict


def _to_verdict(signals: RecoverySignals, investigation: InvestigationResult | None) -> AgentVerdict:
    if signals.status != "failed":
        # General check, not a "successful retry" special case: whatever
        # made this payment not currently failed -- captured on attempt 1,
        # or a later attempt's ActionOutcomeObserved(SUCCESS) folded in by
        # projection.py -- there is nothing to recover. Must run before the
        # failure_reason/category branch below: a resolved payment has
        # failure_reason=None, which FAILURE_TAXONOMY.get(None) would
        # otherwise misclassify as "unrecognized category" (ATTEMPT_MODEL_SPEC.md).
        decision, action, score = "DO_NOT_RETRY", "NONE", 1.0
        reason = f"payment {signals.payment_id} is not currently failed (status={signals.status!r}) -- nothing to recover"
    elif signals.has_alternate_success:
        decision, action, score = "DO_NOT_RETRY", "NONE", 1.0
        reason = (f"another payment on the same order as {signals.payment_id} already succeeded -- "
                  f"retrying would risk a duplicate charge")
    elif not signals.known_category:
        decision, action, score = "INVESTIGATE", "MANUAL_REVIEW", 0.0
        reason = f"unrecognized failure_reason={signals.failure_reason!r}"
    elif not signals.is_recoverable_category:
        decision, action, score = "ESCALATE", signals.default_action, 0.0
        reason = f"failure_reason={signals.failure_reason} is not a recoverable category"
    else:
        decision, action, score = "RETRY", signals.default_action, signals.base_success_rate
        reason = (f"failure_reason={signals.failure_reason} is recoverable; category's own historical "
                  f"retry-success rate is {signals.base_success_rate:.0%} "
                  f"(a base rate, not a per-instance guess)")

    investigation_confidence = None
    investigation_id = None
    if investigation is not None and investigation.executed_4b:
        investigation_id = signals.payment_id
        investigation_confidence = investigation.investigation_confidence
        if investigation.narrative:
            reason = investigation.narrative

    return AgentVerdict(
        agent="recovery", subject=signals.payment_id, decision=decision, reason=reason,
        evidence=signals.evidence, decision_score=score, investigation_confidence=investigation_confidence,
        proposed_action=action, investigation_id=investigation_id,
        metrics={"base_success_rate": signals.base_success_rate,
                  "has_alternate_success": float(signals.has_alternate_success),
                  "has_prior_failed_attempts": float(signals.has_prior_failed_attempts)},
        affected_entities=[signals.payment_id],
    )


def run_recovery_for_payment(graph: GraphRepository, payment_id: str, investigate: bool = False) -> AgentVerdict:
    signals = compute_recovery_signals(graph, payment_id)

    investigation = None
    if not signals.known_category and investigate:
        request = InvestigationRequest(
            subject_type="Payment", subject_id=payment_id,
            question_text=f"Payment {payment_id} failed with an unrecognized reason. What evidence "
                          f"exists about this payment that could explain the failure and inform "
                          f"whether it's worth retrying?",
        )
        prefilled = InvestigationResult(
            request=request, status=InvestigationStatus.UNEXPLAINED, evidence=signals.evidence,
        )
        investigation = investigate_evidence(request, prefilled, graph)

    return _to_verdict(signals, investigation)
