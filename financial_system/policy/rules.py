"""
Deterministic policy rules -- first-matching-rule wins, like a real policy
engine. Every rule reads `decision_score`, `agent`, `proposed_action`, and
whether a cross-domain conflict was detected; NONE reads
`investigation_confidence`. That omission is the entire point of this file:
Discovery.AI's confidence in an explanation is not authorization to act on
money. `decision_score` is always the domain agent's own deterministic
number (reconciliation match, risk signal weight, retry base rate) -- never
anything Discovery.AI produced.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from financial_system.verdict import AgentVerdict

# Bump by hand whenever RULES (or RETRY_ALLOW_THRESHOLD) changes --
# DecisionRecord's policy_version (DECISION_PROVENANCE_SPEC.md question 9).
POLICY_RULES_VERSION = "policy-v1"

RETRY_ALLOW_THRESHOLD = 0.5  # Recovery's own category base-success-rates from Phase 7's real data:
                              # technical_failure=.85, timeout=.80 clear this; insufficient_funds=.45,
                              # authentication_failure=.55 (borderline), issuer_declined=.20 don't --
                              # not an arbitrary cutoff, it's where Phase 7's actual categories split.


@dataclass
class PolicyRule:
    rule_id: str
    description: str
    predicate: Callable[[AgentVerdict, bool], bool]
    outcome: str  # ALLOW | BLOCK | ESCALATE | REVIEW


RULES: list[PolicyRule] = [
    PolicyRule(
        "R1_CONFLICT_ESCALATE",
        "A cross-domain conflict was detected for this subject -- escalate regardless of any single score.",
        lambda v, conflict: conflict,
        "ESCALATE",
    ),
    PolicyRule(
        "R2_RISK_HOLD_BLOCK",
        "Risk proposes HOLD_PAYMENT -- block pending action on this entity.",
        lambda v, conflict: v.agent == "risk" and v.proposed_action == "HOLD_PAYMENT",
        "BLOCK",
    ),
    PolicyRule(
        "R3_RECOVERY_RETRY_ALLOW",
        f"Recovery proposes a retry with decision_score >= {RETRY_ALLOW_THRESHOLD} "
        f"(the category's own historical base success rate).",
        lambda v, conflict: (v.agent == "recovery" and v.proposed_action.startswith("RETRY")
                              and v.decision_score >= RETRY_ALLOW_THRESHOLD),
        "ALLOW",
    ),
    PolicyRule(
        "R4_RECOVERY_RETRY_LOW_SCORE_REVIEW",
        f"Recovery proposes a retry with decision_score < {RETRY_ALLOW_THRESHOLD} -- not auto-approved.",
        lambda v, conflict: v.agent == "recovery" and v.proposed_action.startswith("RETRY"),
        "REVIEW",
    ),
    PolicyRule(
        "R5_CONTROLLER_CLEAN_ALLOW",
        "Controller decision is PASS or RESOLVE -- reconciliation is clean or fully explained.",
        lambda v, conflict: v.agent == "controller" and v.decision in ("PASS", "RESOLVE"),
        "ALLOW",
    ),
    PolicyRule(
        "R6_CONTROLLER_UNRESOLVED_ESCALATE",
        "Controller decision is REVIEW or INVESTIGATE -- an unresolved reconciliation exception.",
        lambda v, conflict: v.agent == "controller" and v.decision in ("REVIEW", "INVESTIGATE"),
        "ESCALATE",
    ),
    PolicyRule(
        "R7_RISK_RELEASE_ALLOW",
        "Risk decision is RELEASE (low decision_score) -- no network-risk signal found.",
        lambda v, conflict: v.agent == "risk" and v.decision == "RELEASE",
        "ALLOW",
    ),
    PolicyRule(
        "R8_RISK_REVIEW",
        "Risk decision is REVIEW (medium decision_score) -- worth a human look, not an auto-block.",
        lambda v, conflict: v.agent == "risk" and v.decision == "REVIEW",
        "REVIEW",
    ),
    PolicyRule(
        "R9_RECOVERY_ESCALATE",
        "Recovery decision is ESCALATE or INVESTIGATE -- a non-recoverable or unrecognized category.",
        lambda v, conflict: v.agent == "recovery" and v.decision in ("ESCALATE", "INVESTIGATE"),
        "ESCALATE",
    ),
    PolicyRule(
        "R10_RECOVERY_DO_NOT_RETRY_ALLOW",
        "Recovery decision is DO_NOT_RETRY -- correctly declining to act, not a blocked action.",
        lambda v, conflict: v.agent == "recovery" and v.decision == "DO_NOT_RETRY",
        "ALLOW",
    ),
    PolicyRule(
        "R99_DEFAULT_REVIEW",
        "No rule matched -- default to REVIEW, never silently ALLOW an unrecognized case.",
        lambda v, conflict: True,
        "REVIEW",
    ),
]
