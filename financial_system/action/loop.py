"""
Phase 10: the closed loop -- Policy -> Action -> Verification -> (close the
case, or re-investigate -> new decision -> Policy -> Action again). Recovery's
RETRY decision is the flagship demonstration: `decision_score` is a category
base rate (recovery/signals.py), never a per-instance guarantee, so a real
per-instance FAILURE is the honest, expected outcome some of the time -- not
a bug to route around.

Zero LLM by default (investigate=False), same discipline as Phases 5, 8, 9:
Discovery.AI, if enabled, is invoked only after a genuine FAILURE, and its
narrative is attached as context for a human -- it never drives what happens
next. The next action is always the same deterministic rule: don't retry an
identical failed action again blindly; escalate.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from financial_system.action.models import ActionAttempt, ActionCase
from financial_system.action.simulator import execute_action, verify_retry
from financial_system.decisions.models import DecisionRecord
from financial_system.financial_graph.repository import GraphRepository
from financial_system.policy.engine import PolicyDecision, evaluate
from financial_system.recovery.expected_value import compute_expected_value
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.recovery.signals import RECOVERY_LOGIC_VERSION
from financial_system.policy.rules import POLICY_RULES_VERSION
from financial_system.verdict import AgentVerdict

MAX_ATTEMPTS = 2


def _record_consequential_decision(decisions, verdict: AgentVerdict, policy_decision: PolicyDecision,
                                    payment_id: str, idempotency_key: str, actions, world_as_of) -> None:
    """DECISION_PROVENANCE_SPEC.md's smallest possible record -- a
    fingerprint of the reasoning that authorized an Action, not a frozen
    copy of the Verdict (evidence/reason travel; 4A's raw Finding values
    don't, since they're reproducible from world_as_of + logic_version).
    Only called for policy_decision.outcome == "ALLOW" -- the spec's own
    definition of consequential."""
    now = datetime.now(timezone.utc)
    action = actions.get_by_idempotency_key(idempotency_key)
    decisions.record(DecisionRecord(
        decision_id=str(uuid.uuid4()), case_id=payment_id, subject=verdict.subject,
        agent=verdict.agent, decision=verdict.decision, decision_score=verdict.decision_score,
        reason=verdict.reason, evidence=verdict.evidence,
        policy_outcome=policy_decision.outcome, policy_rule_id=policy_decision.rule_id,
        world_as_of=world_as_of or now, logic_version=RECOVERY_LOGIC_VERSION,
        policy_version=POLICY_RULES_VERSION, investigation_id=verdict.investigation_id,
        created_at=now, action_id=action.action_id if action else None,
    ))
    decisions.commit()


def _escalate_after_failed_retry(verdict: AgentVerdict, narrative: str | None) -> AgentVerdict:
    """The next decision after a failed retry -- deterministic, never a
    repeat of the same action. `narrative` (Discovery.AI's, if gathered) is
    carried into `reason` purely as context; investigation_confidence is
    explicitly None here regardless of what Discovery.AI reported, because
    nothing about this escalation is authorized by that number."""
    reason = "retry attempt failed -- escalating rather than retrying again blindly"
    if narrative:
        reason = f"{narrative} | {reason}"
    return AgentVerdict(
        agent="recovery", subject=verdict.subject, decision="ESCALATE", reason=reason,
        evidence=verdict.evidence, decision_score=0.0, investigation_confidence=None,
        proposed_action="MANUAL_REVIEW", affected_entities=verdict.affected_entities,
    )


def _investigate_failure(graph: GraphRepository, payment_id: str, evidence: list[str]) -> str | None:
    from financial_system.discovery_adapter.investigate import investigate_evidence
    from financial_system.discovery_adapter.models import (
        InvestigationRequest, InvestigationResult, InvestigationStatus,
    )

    request = InvestigationRequest(
        subject_type="Payment", subject_id=payment_id,
        question_text=f"A retry attempt on payment {payment_id} failed. What evidence about this "
                      f"payment or its order might explain why, or whether a different recovery "
                      f"approach is worth trying?",
    )
    prefilled = InvestigationResult(request=request, status=InvestigationStatus.UNEXPLAINED, evidence=evidence)
    inv = investigate_evidence(request, prefilled, graph)
    return inv.narrative if inv.executed_4b else None


def run_action_loop(graph: GraphRepository, payment_id: str, investigate: bool = False,
                     max_attempts: int = MAX_ATTEMPTS) -> ActionCase:
    case = ActionCase(subject=payment_id)
    verdict = run_recovery_for_payment(graph, payment_id, investigate=False)

    attempt_number = 1
    while True:
        policy_decision = evaluate(verdict, has_conflict=False)
        executed, action_taken, log = execute_action(verdict, policy_decision)

        verification_result = None
        verification_detail = ""
        if executed and action_taken.startswith("RETRY"):
            verification_result, verification_detail = verify_retry(payment_id)

        case.attempts.append(ActionAttempt(
            attempt_number=attempt_number, verdict=verdict, policy_decision=policy_decision,
            executed=executed, action_taken=action_taken, execution_log=log,
            verification_result=verification_result, verification_detail=verification_detail,
        ))

        if verification_result == "SUCCESS":
            case.case_status = "RESOLVED"
            return case

        if verification_result == "FAILURE":
            if attempt_number >= max_attempts:
                case.case_status = "ESCALATED"
                return case
            narrative = _investigate_failure(graph, payment_id, verdict.evidence) if investigate else None
            verdict = _escalate_after_failed_retry(verdict, narrative)
            attempt_number += 1
            continue

        # Not executed at all (BLOCK/ESCALATE/REVIEW) -- nothing to verify;
        # the case closes at whatever status Policy already assigned.
        case.case_status = policy_decision.outcome
        return case


def run_action_loop_v2(graph: GraphRepository, payment_id: str, events, actions,
                        investigate: bool = False, max_attempts: int = MAX_ATTEMPTS,
                        decisions=None, world_as_of=None) -> ActionCase:
    """Stage 3: identical control flow to run_action_loop() -- same decisions,
    same case_status/attempt outcomes -- but every execution now goes through
    execute_action_with_events(), which is durable and idempotent. `events`/
    `actions` are an EventStore/ActionStore the caller owns (so a test can
    inspect them afterward). correlation_id/case_id = payment_id (§1a: they
    default equal for this migration).

    `decisions` (a DecisionStore, optional) and `world_as_of` (the cutoff
    the caller believes `graph` reflects, optional -- defaults to "now" at
    record time, since nothing in this live loop actually builds `graph`
    from an as_of-filtered snapshot yet, per DECISION_PROVENANCE_SPEC.md's
    own honesty about that gap) are both purely additive: omitting either
    reproduces this function's exact pre-existing behavior. When
    `decisions` is given, a DecisionRecord is written for every
    CONSEQUENTIAL decision this loop makes (policy_decision.outcome ==
    "ALLOW", spec question 1) -- never for BLOCK/ESCALATE/REVIEW, which
    stay exactly as ephemeral as every Finding already is."""
    from financial_system.action.event_execution import execute_action_with_events

    case = ActionCase(subject=payment_id)
    verdict = run_recovery_for_payment(graph, payment_id, investigate=False)

    # attempt_number here is ActionCase's own pre-existing concept: the Nth
    # attempt THIS RETRY LOOP has made (1-based, unchanged from Phase 10).
    # It is NOT the ontology's overall attempt_number (ATTEMPT_MODEL_SPEC.md
    # Q2: attempt 1 is the original PaymentCreated/terminal event, so the
    # first retry is overall attempt 2) -- overall_attempt is that separate,
    # ontology-correct number, used only for the event payload and the
    # idempotency key, and never fed back into ActionCase/ActionAttempt.
    attempt_number = 1
    while True:
        # Captured BEFORE execute_action_with_events runs -- world_as_of must
        # reflect the world this verdict actually reasoned over, not the
        # world after this very iteration's own outcome event lands (which
        # would retroactively make the decision look like it already knew
        # its own result). Real bug found and fixed at this checkpoint, not
        # a hypothetical: an earlier version of this function stamped
        # world_as_of AFTER execute_action_with_events returned, and a
        # historical replay at that cutoff reproduced DO_NOT_RETRY instead
        # of the RETRY that was actually decided.
        reasoning_time = datetime.now(timezone.utc)
        # EV/R0 (Block 5/Phase 5-6): the same expected-value gate already
        # proven against 144 real payments and demonstrated in the live demo
        # is now part of the ACTUAL consequential path, not just an analytical
        # branch alongside it. compute_expected_value() returns None for any
        # verdict it has nothing to say about (not a RETRY-eligible recovery
        # case) -- evaluate()'s R0 rule already only matches a recovery
        # verdict proposing RETRY, so passing a None or inapplicable
        # ev_result here is always safe and never changes behavior for a
        # non-Recovery-RETRY verdict (e.g. the escalate verdict on a second
        # attempt). as_of is intentionally NOT overridden here -- Block 5's
        # own default (the payment's own created_at) is the correct decision
        # moment, not "now".
        ev_result = compute_expected_value(graph, payment_id)
        policy_decision = evaluate(verdict, has_conflict=False, ev_result=ev_result)
        overall_attempt = attempt_number + 1
        idempotency_key = f"{payment_id}:attempt{overall_attempt}:{policy_decision.proposed_action}"
        executed, action_taken, log, verification_result, verification_detail = execute_action_with_events(
            verdict, policy_decision, idempotency_key, case_id=payment_id, events=events, actions=actions,
            attempt_number=overall_attempt,
        )

        if decisions is not None and policy_decision.outcome == "ALLOW":
            _record_consequential_decision(decisions, verdict, policy_decision, payment_id,
                                            idempotency_key, actions, world_as_of or reasoning_time)

        case.attempts.append(ActionAttempt(
            attempt_number=attempt_number, verdict=verdict, policy_decision=policy_decision,
            executed=executed, action_taken=action_taken, execution_log=log,
            verification_result=verification_result, verification_detail=verification_detail,
        ))

        if verification_result == "SUCCESS":
            case.case_status = "RESOLVED"
            return case

        if verification_result == "FAILURE":
            if attempt_number >= max_attempts:
                case.case_status = "ESCALATED"
                return case
            narrative = _investigate_failure(graph, payment_id, verdict.evidence) if investigate else None
            verdict = _escalate_after_failed_retry(verdict, narrative)
            attempt_number += 1
            continue

        case.case_status = policy_decision.outcome
        return case
