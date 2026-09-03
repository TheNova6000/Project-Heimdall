"""
ActionAttempt/ActionCase -- an append-only audit chain. A follow-up attempt
after a FAILURE never overwrites the original: attempts accumulate, each one
carrying its own verdict/policy/execution/verification, so "what did we
originally decide, what did we do, what actually happened, what did we do
next" all stay independently inspectable.

Action (Stage 3, MIGRATION_DESIGN.md §9) -- the durable command object. This
is the ONE object in the whole system explicitly allowed to mutate a field
in place (`execution_status`): it's tracking the COMMAND's own lifecycle
(PENDING -> STARTED -> COMPLETED/FAILED/REJECTED), not the financial world's.
The financial world only ever learns from `ActionOutcomeObserved` events,
never from Action.execution_status directly -- that boundary is what makes
Stage 4 (closed-loop replay) possible later.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from financial_system.policy.engine import PolicyDecision
from financial_system.verdict import AgentVerdict


class Action(BaseModel):
    action_id: str
    idempotency_key: str
    case_id: str                    # == correlation_id on its events (§1a)
    subject_id: str
    action_type: str
    proposed_by: str                 # agent name
    authorized_by: str                # policy rule_id
    preconditions: dict[str, Any] = {}
    expected_effect: str = ""
    created_at: datetime
    execution_started_at: Optional[datetime] = None
    execution_completed_at: Optional[datetime] = None
    execution_status: str = "PENDING"   # PENDING | STARTED | COMPLETED | FAILED | REJECTED
    result: Optional[dict[str, Any]] = None


class ActionAttempt(BaseModel):
    attempt_number: int
    verdict: AgentVerdict
    policy_decision: PolicyDecision
    executed: bool
    action_taken: str
    execution_log: str
    verification_result: Optional[str] = None   # "SUCCESS" | "FAILURE" | None (nothing to verify)
    verification_detail: str = ""


class ActionCase(BaseModel):
    subject: str
    attempts: list[ActionAttempt] = []
    case_status: str = "OPEN"   # RESOLVED | OPEN | ESCALATED | BLOCKED | REVIEW
