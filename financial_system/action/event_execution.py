"""
Stage 3 (MIGRATION_DESIGN.md §9): the idempotent, event-emitting action
executor. Same conceptual job as simulator.py's execute_action(), but:
  - durable: creates a real Action row before doing anything
  - idempotent: same idempotency_key + same parameters -> cached result,
    never re-executed
  - safe under a same-key-different-parameters reuse -> rejected
  - safe under a simulated crash mid-execution -> recovers from the event
    log rather than blindly re-executing

No action event mutates financial state merely by being requested or
started. Only `ActionOutcomeObserved` represents evidence of what actually
happened -- exactly the invariant this stage exists to prove.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from financial_system.action.action_store import ActionStore
from financial_system.action.models import Action
from financial_system.action.simulator import verify_retry
from financial_system.events.models import Event
from financial_system.events.store import EventStore
from financial_system.policy.engine import PolicyDecision
from financial_system.verdict import AgentVerdict


def _request_signature(verdict: AgentVerdict, policy_decision: PolicyDecision) -> dict:
    return {"agent": verdict.agent, "subject": verdict.subject, "decision": verdict.decision,
            "proposed_action": policy_decision.proposed_action, "policy_outcome": policy_decision.outcome}


def execute_action_with_events(
    verdict: AgentVerdict, policy_decision: PolicyDecision, idempotency_key: str, case_id: str,
    events: EventStore, actions: ActionStore, attempt_number: int = 1,
) -> tuple[bool, str, str, str | None, str]:
    """Returns (executed, action_taken, log, verification_result, verification_detail)."""
    request_signature = _request_signature(verdict, policy_decision)
    existing = actions.get_by_idempotency_key(idempotency_key)

    if existing is not None:
        if existing.preconditions != request_signature:
            return False, "REJECTED", (
                f"idempotency key {idempotency_key!r} reused with different parameters -- rejected"
            ), None, ""

        if existing.execution_status in ("COMPLETED", "FAILED", "REJECTED"):
            r = existing.result or {}
            return (r.get("executed", False), r.get("action_taken", "NONE"),
                    f"IDEMPOTENT REPLAY: returning cached result for {idempotency_key!r}",
                    r.get("verification_result"), r.get("verification_detail", ""))

        if existing.execution_status == "STARTED":
            # Crash-recovery path: ActionExecutionStarted was recorded but Action's
            # own status was never advanced. Check the event log itself for evidence
            # -- never blindly re-execute.
            outcome_events = [e for e in events.events_for_subject(verdict.subject, "ActionOutcomeObserved")
                               if e.payload.get("action_id") == existing.action_id]
            if outcome_events:
                outcome = outcome_events[-1].payload
                completed_at = datetime.now(timezone.utc)
                status = "COMPLETED" if outcome.get("verification_result") != "FAILURE" else "FAILED"
                actions.update_execution_status(existing.action_id, status, completed_at=completed_at,
                                                 result=outcome)
                actions.commit()
                return (outcome.get("executed", False), outcome.get("action_taken", "NONE"),
                        "RECOVERED: outcome was already observed before the crash",
                        outcome.get("verification_result"), outcome.get("verification_detail", ""))
            return (False, "NONE",
                    f"action {existing.action_id} is already in-flight (STARTED, no observed outcome) -- "
                    f"refusing to execute a second time without evidence of the first attempt's outcome",
                    None, "")

    # No existing action for this key -- create it, emit ActionRequested.
    now = datetime.now(timezone.utc)
    action = Action(
        action_id=str(uuid.uuid4()), idempotency_key=idempotency_key, case_id=case_id,
        subject_id=verdict.subject, action_type=policy_decision.proposed_action,
        proposed_by=verdict.agent, authorized_by=policy_decision.rule_id,
        preconditions=request_signature,
        expected_effect=f"{policy_decision.outcome}: {policy_decision.proposed_action}",
        created_at=now, execution_status="PENDING",
    )
    actions.create(action)
    requested_event = Event(
        event_id=str(uuid.uuid4()), event_type="ActionRequested", subject_id=verdict.subject,
        source="policy_engine", occurred_at=now, recorded_at=now,
        payload={"action_id": action.action_id, "idempotency_key": idempotency_key,
                 "attempt_number": attempt_number, **request_signature},
        correlation_id=case_id,
    )
    events.append(requested_event)
    events.commit()

    if policy_decision.outcome != "ALLOW":
        result = {"executed": False, "action_taken": "NONE"}
        actions.update_execution_status(action.action_id, "REJECTED", result=result)
        actions.commit()
        return (False, "NONE", f"not executed -- policy outcome was {policy_decision.outcome}, not ALLOW",
                None, "")

    started_at = datetime.now(timezone.utc)
    actions.update_execution_status(action.action_id, "STARTED", started_at=started_at)
    actions.commit()
    started_event = Event(
        event_id=str(uuid.uuid4()), event_type="ActionExecutionStarted", subject_id=verdict.subject,
        source="action_executor", occurred_at=started_at, recorded_at=started_at,
        payload={"action_id": action.action_id, "attempt_number": attempt_number}, correlation_id=case_id,
        causation_id=requested_event.event_id,
    )
    events.append(started_event)
    events.commit()

    action_taken = policy_decision.authorized_action or "NONE"
    verification_result, verification_detail = (None, "")
    if action_taken.startswith("RETRY"):
        verification_result, verification_detail = verify_retry(verdict.subject)

    outcome_payload = {
        "action_id": action.action_id, "executed": True, "action_taken": action_taken,
        "verification_result": verification_result, "verification_detail": verification_detail,
        "attempt_number": attempt_number,
    }
    completed_at = datetime.now(timezone.utc)
    events.append(Event(
        event_id=str(uuid.uuid4()), event_type="ActionOutcomeObserved", subject_id=verdict.subject,
        source="gateway_simulator" if action_taken.startswith("RETRY") else "action_executor",
        occurred_at=completed_at, recorded_at=completed_at, payload=outcome_payload,
        correlation_id=case_id, causation_id=started_event.event_id,
    ))
    events.commit()

    final_status = "FAILED" if verification_result == "FAILURE" else "COMPLETED"
    actions.update_execution_status(action.action_id, final_status, completed_at=completed_at,
                                     result=outcome_payload)
    actions.commit()

    log = f"SIMULATED: executed {action_taken} for {verdict.subject} (no real API called)"
    return True, action_taken, log, verification_result, verification_detail
