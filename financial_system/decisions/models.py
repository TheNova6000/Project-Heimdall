"""
DecisionRecord -- the smallest durable trace of a CONSEQUENTIAL decision,
per DECISION_PROVENANCE_SPEC.md's candidate model. Deliberately not a
frozen copy of AgentVerdict: 4A stays reproducible from
(world_as_of, logic_version, deterministic inputs), 4B stays a reference
(investigation_id), never embedded. See the spec for the full reasoning,
including the named, honest limitation that world_as_of pins event-sourced
financial state only -- not reference tables or entity_matches (spec's
"Resolving logic_version completeness" section).

A decision is consequential exactly when PolicyDecision.outcome == "ALLOW"
(spec question 1) -- everything upstream of that point stays ephemeral,
same as every Finding always has.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DecisionRecord(BaseModel):
    decision_id: str
    case_id: str                       # == Action.case_id, when an Action follows
    subject: str
    agent: str                          # "controller" | "risk" | "recovery"
    decision: str                       # e.g. RETRY
    decision_score: float
    reason: str
    evidence: list[str] = []

    policy_outcome: str                 # always "ALLOW" -- consequential by definition
    policy_rule_id: str

    world_as_of: datetime               # cutoff the event-sourced state was frozen at;
                                          # does NOT pin reference tables or entity_matches
    logic_version: str
    policy_version: str
    investigation_id: Optional[str] = None   # set only when 4B actually ran

    created_at: datetime
    action_id: Optional[str] = None      # set once the authorized Action exists
