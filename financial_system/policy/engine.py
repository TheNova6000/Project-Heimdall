"""
Phase 9: Policy Engine. Pure function over an AgentVerdict + a conflict flag
(+ an optional pre-computed ExpectedValueResult, Phase 5 of the expected-value
Recovery upgrade) -> PolicyDecision, evaluated against RULES in order, first
match wins. Deterministic, auditable: every decision carries the exact
rule_id and description that fired, so "why did the system allow/block/
escalate this" always has a literal answer -- no LLM anywhere in this file.

`ev_result` is opt-in: existing callers that don't pass it get byte-for-byte
identical PolicyDecision.outcome/rule_id behavior to before this rule
existed (R0's predicate is False whenever ev_result is None), so nothing
already proven (Phase 9's 5 required cases, the live demo) is affected
unless a caller explicitly starts computing and passing EV.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from financial_system.policy.rules import RULES
from financial_system.recovery.expected_value import ExpectedValueResult
from financial_system.verdict import AgentVerdict


class PolicyDecision(BaseModel):
    subject: str
    agent: str
    outcome: str  # ALLOW | BLOCK | ESCALATE | REVIEW
    rule_id: str
    rule_description: str
    decision_score: float
    proposed_action: str
    authorized_action: Optional[str] = None
    # Deliberately no investigation_confidence field here -- it lives on the
    # source AgentVerdict for audit only. Copying it onto the decision would
    # invite a future caller to read it as if it mattered to authorization.

    # Populated only when the caller supplies ev_result -- present regardless
    # of which rule ultimately fires, so a positive-EV ALLOW still carries
    # its own economics on the record, not just a BLOCKed one.
    ev_expected_value: Optional[float] = None
    ev_explanation: Optional[str] = None


def evaluate(verdict: AgentVerdict, has_conflict: bool = False,
             ev_result: Optional[ExpectedValueResult] = None) -> PolicyDecision:
    ev_explanation = None
    if ev_result is not None:
        ev_explanation = (
            f"value=Rs.{ev_result.value:.2f} x base_success_rate={ev_result.base_success_rate:.2f} "
            f"- fee(2%)=Rs.{ev_result.fee_cost:.2f} "
            f"- fraud_harm(tier={ev_result.risk_tier}, rate={ev_result.harm_rate:.3f})=Rs.{ev_result.harm_cost:.2f} "
            f"= EV Rs.{ev_result.expected_value:.2f}"
        )

    for rule in RULES:
        if rule.predicate(verdict, has_conflict, ev_result):
            return PolicyDecision(
                subject=verdict.subject, agent=verdict.agent, outcome=rule.outcome,
                rule_id=rule.rule_id, rule_description=rule.description,
                decision_score=verdict.decision_score, proposed_action=verdict.proposed_action,
                authorized_action=verdict.proposed_action if rule.outcome == "ALLOW" else None,
                ev_expected_value=ev_result.expected_value if ev_result is not None else None,
                ev_explanation=ev_explanation,
            )
    raise AssertionError("R99_DEFAULT_REVIEW matches everything -- unreachable")
