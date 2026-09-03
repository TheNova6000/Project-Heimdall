"""
Phase 6: Risk agent.

Same boundary as Controller (reconciliation/controller.py): deterministic
signals decide the score and tier (risk/signals.py, risk/scoring.py, zero
LLM), Discovery.AI is only ever asked to explain an already-HIGH-tier device,
never to produce the score itself. `decision`/`proposed_action` come from
`risk_tier()` alone; `investigation_confidence` is carried for audit only.

    Device (>=2 sharing customers)
              |
      compute_device_risk_signals()  (signals.py)
              |
        score_signals()  (scoring.py)
              |
       +------+------+------+
       |      |      |
      LOW   MEDIUM  HIGH
      RELEASE REVIEW HOLD
                       |
                (if investigate=True)
                       |
                 Discovery.AI: "why does this look risky?"
                       |
                 reason / investigation_confidence only --
                 never overwrites decision/proposed_action
"""
from __future__ import annotations

from financial_system.discovery_adapter.investigate import investigate_evidence
from financial_system.discovery_adapter.models import InvestigationRequest, InvestigationResult, InvestigationStatus
from financial_system.financial_graph.repository import GraphRepository
from financial_system.risk.scoring import risk_tier, score_signals
from financial_system.risk.signals import RiskSignals, compute_device_risk_signals
from financial_system.verdict import AgentVerdict

_TIER_DECISION = {
    "LOW": ("RELEASE", "NONE"),
    "MEDIUM": ("REVIEW", "MANUAL_REVIEW"),
    "HIGH": ("HOLD", "HOLD_PAYMENT"),
}


def _to_verdict(signals: RiskSignals, score: float, metrics: dict[str, float],
                 investigation: InvestigationResult | None) -> AgentVerdict:
    tier = risk_tier(score)
    decision, action = _TIER_DECISION[tier]

    reason = (f"{signals.n_sharers} customer(s) share device {signals.device_id}: "
              f"max_burst_count={signals.max_burst_count} payments/60min, "
              f"burst_amount_cov={signals.burst_amount_cov}, "
              f"min_account_age_days={signals.min_account_age_days}") \
        if signals.n_sharers > 1 else "no device sharing observed"

    investigation_confidence = None
    investigation_id = None
    if investigation is not None and investigation.executed_4b:
        investigation_id = signals.device_id
        investigation_confidence = investigation.investigation_confidence
        if investigation.narrative:
            reason = investigation.narrative

    return AgentVerdict(
        agent="risk", subject=signals.device_id, decision=decision, reason=reason,
        evidence=signals.evidence, decision_score=score,
        investigation_confidence=investigation_confidence, proposed_action=action,
        investigation_id=investigation_id,
        metrics={**metrics, "n_sharers": float(signals.n_sharers),
                  "max_burst_count": float(signals.max_burst_count),
                  "burst_amount_cov": signals.burst_amount_cov or 0.0},
        affected_entities=signals.sharer_customer_ids,
    )


def run_risk_for_device(graph: GraphRepository, device_id: str, investigate: bool = False) -> AgentVerdict:
    signals = compute_device_risk_signals(graph, device_id)
    score, metrics = score_signals(signals)
    tier = risk_tier(score)

    investigation = None
    if tier == "HIGH" and investigate:
        request = InvestigationRequest(
            subject_type="Device", subject_id=device_id,
            question_text=f"Device {device_id} is shared by {signals.n_sharers} customers, with "
                          f"{signals.max_burst_count} payments falling inside a single 60-minute "
                          f"window and minimum account age {signals.min_account_age_days} days. Is "
                          f"this pattern consistent with a fraud ring, or a plausible benign "
                          f"explanation (e.g. a shared family/office device)?",
        )
        prefilled = InvestigationResult(
            request=request, status=InvestigationStatus.UNEXPLAINED,
            facts=[f"device shared by {signals.n_sharers} customers"], evidence=signals.evidence,
        )
        investigation = investigate_evidence(request, prefilled, graph)

    return _to_verdict(signals, score, metrics, investigation)
