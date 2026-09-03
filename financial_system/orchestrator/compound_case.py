"""
CompoundCase -- the merge target for Phase 8. Deliberately does NOT flatten
Controller/Risk/Recovery into one score: each verdict is preserved whole and
labeled by its own agent, exactly per the rule "don't flatten the three
verdicts into one score." shared_entities/shared_evidence are the dedup
union across whichever verdicts are present; conflicts are explicit strings,
never silently averaged away.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from financial_system.discovery_adapter.models import InvestigationResult
from financial_system.verdict import AgentVerdict


class CompoundCase(BaseModel):
    subject: str                        # the anchor entity -- a payment_id
    triggered_events: list[str] = []
    invoked_agents: list[str] = []

    controller_verdict: Optional[AgentVerdict] = None
    risk_verdict: Optional[AgentVerdict] = None
    recovery_verdict: Optional[AgentVerdict] = None

    shared_entities: list[str] = []
    shared_evidence: list[str] = []
    investigations: list[str] = []      # non-null investigation_ids across verdicts
    conflicts: list[str] = []

    # Populated only when a real conflict exists AND the caller opts into
    # investigate=True -- Discovery.AI reasoning over the SPECIFIC evidence
    # behind a genuine cross-domain disagreement, using the real multi-step
    # loop (financial_system/discovery_adapter/investigate.py). Purely
    # explanatory: this NEVER feeds back into controller_verdict/risk_verdict/
    # recovery_verdict's decision/decision_score/proposed_action, or into the
    # EV/Policy pipeline -- same kind-1 decides/kind-3 explains firewall this
    # project has enforced everywhere else.
    conflict_investigation: Optional[InvestigationResult] = None


def _dedup(*lists: list[str]) -> list[str]:
    seen: list[str] = []
    for lst in lists:
        for x in lst:
            if x not in seen:
                seen.append(x)
    return seen


def detect_conflicts(controller: AgentVerdict | None, risk: AgentVerdict | None,
                      recovery: AgentVerdict | None) -> list[str]:
    """Small, explicit rule set -- the cross-domain interactions that actually
    matter for this system, not an exhaustive combinatorial matrix built on
    speculation. Each rule names a real reason two independent, correct
    verdicts still deserve a human's attention together."""
    conflicts = []
    if risk is not None and risk.decision == "HOLD" and recovery is not None and recovery.decision == "RETRY":
        conflicts.append(
            "Risk flags HOLD on this customer's device while Recovery independently proposes RETRY "
            "on this payment -- recommend REVIEW before executing the retry."
        )
    if (controller is not None and controller.decision == "INVESTIGATE"
            and risk is not None and risk.decision == "HOLD"):
        conflicts.append(
            "An unexplained reconciliation gap and a high-risk device pattern both touch this case -- "
            "escalate as one compound signal, not two independent low-priority items."
        )
    return conflicts


def merge(subject: str, events: list[str], invoked_agents: list[str],
          controller: AgentVerdict | None, risk: AgentVerdict | None,
          recovery: AgentVerdict | None) -> CompoundCase:
    verdicts = [v for v in (controller, risk, recovery) if v is not None]
    shared_entities = _dedup(*[v.affected_entities for v in verdicts])
    shared_evidence = _dedup(*[v.evidence for v in verdicts])
    investigations = [v.investigation_id for v in verdicts if v.investigation_id]

    return CompoundCase(
        subject=subject, triggered_events=events, invoked_agents=invoked_agents,
        controller_verdict=controller, risk_verdict=risk, recovery_verdict=recovery,
        shared_entities=shared_entities, shared_evidence=shared_evidence,
        investigations=investigations, conflicts=detect_conflicts(controller, risk, recovery),
    )
