"""
AgentVerdict -- the common language every domain agent (Controller now, Risk
and Recovery later) speaks, per ARCHITECTURE.md §4. First real implementation;
until Phase 5 this only existed as a design-doc shape.

`decision_score` is always computed by the agent's own deterministic logic.
`investigation_confidence` is carried through from Discovery.AI purely for
audit -- nothing reads it to decide anything. That split is the whole point:
kind-1 (deterministic) intelligence decides, kind-3 (investigative) only
explains.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class AgentVerdict(BaseModel):
    agent: Literal["risk", "controller", "recovery"]
    subject: str                       # entity id: settlement_id, payment_id...
    decision: str                      # e.g. PASS / RESOLVE / REVIEW / INVESTIGATE
    reason: str
    evidence: list[str] = []           # entity ids the decision rests on

    decision_score: float              # deterministic-intelligence score, always agent-computed
    investigation_confidence: Optional[float] = None   # Discovery.AI's own, audit-only

    proposed_action: str
    investigation_id: Optional[str] = None
    metrics: dict[str, float] = {}
    affected_entities: list[str] = []
