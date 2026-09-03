"""
Phase 9: Policy Engine. Pure function over an AgentVerdict + a conflict flag
-> PolicyDecision, evaluated against RULES in order, first match wins.
Deterministic, auditable: every decision carries the exact rule_id and
description that fired, so "why did the system allow/block/escalate this"
always has a literal answer -- no LLM anywhere in this file.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from financial_system.policy.rules import RULES
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


def evaluate(verdict: AgentVerdict, has_conflict: bool = False) -> PolicyDecision:
    for rule in RULES:
        if rule.predicate(verdict, has_conflict):
            return PolicyDecision(
                subject=verdict.subject, agent=verdict.agent, outcome=rule.outcome,
                rule_id=rule.rule_id, rule_description=rule.description,
                decision_score=verdict.decision_score, proposed_action=verdict.proposed_action,
                authorized_action=verdict.proposed_action if rule.outcome == "ALLOW" else None,
            )
    raise AssertionError("R99_DEFAULT_REVIEW matches everything -- unreachable")
