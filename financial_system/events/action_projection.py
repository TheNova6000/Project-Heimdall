"""
Stage 4 Gate 1: the ONLY path from an Action-lifecycle event to financial
state. Structural enforcement, not convention -- this function's first line
makes it impossible for ActionRequested/ActionExecutionStarted to reach the
mutation below, regardless of what future code calls it with.

Deliberately narrow, per the explicit design rule: this turns ONE event
into ONE state transition. It does not recompute a verdict, call Recovery,
reconcile a settlement, or touch Policy -- that's the orchestrator's job,
on the NEXT observation, never this function's. A projector that started
calling agents would be a second business-logic engine, which is exactly
what this stage's design rules forbid.
"""
from __future__ import annotations

from financial_system.events.models import Event
from financial_system.financial_state.store import FinancialStateStore


def project_action_outcome(event: Event, state: FinancialStateStore) -> bool:
    """Returns True if a state transition occurred, False otherwise --
    including, deliberately, for every event this function is structurally
    unable to act on."""
    if event.event_type != "ActionOutcomeObserved":
        return False  # Gate 1: Requested/Started can never reach the mutation below

    payload = event.payload
    if payload.get("verification_result") != "SUCCESS":
        return False  # Gate 5: no phantom facts -- FAILURE or unverified changes nothing

    action_taken = payload.get("action_taken", "")
    if not action_taken.startswith("RETRY"):
        return False

    state.apply_payment_retry_success(event.subject_id, observed_at=event.occurred_at)
    state.commit()
    return True
