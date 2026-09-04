"""
Verification check #4 -- Idempotency (NORTH_STAR.md Section 24: "Was the
action idempotent?").

Bounded exactly as scoped: calling the SAME domain-agent function on the
SAME subject_id against the SAME graph object twice must produce
byte-identical `AgentVerdict` output. This is a decision-idempotency
check (does the intelligence layer answer consistently), not an
action-execution-idempotency check (financial_system/action/'s own
execution_status exactly-once discipline is a different, already-built
piece of the codebase -- see financial_system/financial_state/store.py's
`apply_payment_retry_success` docstring -- and is intentionally out of
scope here; auditing it would mean touching financial_system/action/,
which this task's boundary forbids reading into scope beyond Risk/
Recovery/Controller/graph/state).

Every field of AgentVerdict (pydantic) is compared, via `.model_dump()`,
field by field -- not just `decision`/`decision_score`, since the task
asks for "same decision, same score, same reason string" but a silent
drift in `evidence` order or `metrics` would be exactly the kind of bug
this check exists to catch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from financial_system.verdict import AgentVerdict


@dataclass
class IdempotencyResult:
    agent: str
    subject: str
    identical: bool
    field_diffs: dict[str, tuple[Any, Any]] = field(default_factory=dict)


def check_idempotency(fn: Callable[..., AgentVerdict], *args, **kwargs) -> IdempotencyResult:
    v1 = fn(*args, **kwargs)
    v2 = fn(*args, **kwargs)
    d1, d2 = v1.model_dump(), v2.model_dump()
    diffs = {k: (d1[k], d2[k]) for k in d1 if d1[k] != d2[k]}
    return IdempotencyResult(agent=v1.agent, subject=v1.subject, identical=not diffs, field_diffs=diffs)
