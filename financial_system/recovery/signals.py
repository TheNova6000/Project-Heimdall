"""
Deterministic recovery signals -- zero LLM. `failure_reason` is given
directly by the source data (a real payment gateway publishes a decline-code
taxonomy with documented retry semantics; reading it is a lookup, not
inference). What's genuinely NOT knowable in advance is whether a SPECIFIC
retry attempt will succeed -- recovery_labels.csv's own ground truth encodes
this as two separate facts: `is_recoverable` (category-level: does retrying
this failure TYPE make sense) and `retry_would_succeed` (instance-level:
would THIS retry actually work) -- the exact "recoverable != should retry"
distinction Recovery must preserve, never conflate.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from financial_system.financial_graph.repository import GraphRepository

# Bump by hand whenever FAILURE_TAXONOMY or compute_recovery_signals()/
# recovery_agent.py's decision logic changes -- DecisionRecord's
# logic_version (DECISION_PROVENANCE_SPEC.md question 9). Deliberately a
# plain string, not a real versioning system: cheap enough that "did this
# change" always has a real answer, without inventing infrastructure this
# project doesn't otherwise have (no git repository to hash against).
RECOVERY_LOGIC_VERSION = "recovery-v1"

# A real payment gateway's own decline-code taxonomy -- documented domain
# knowledge, not inferred from this dataset. base_success_rate is the
# category's own historical retry-success rate: the decision score for a
# RETRY action, never a per-instance prediction.
FAILURE_TAXONOMY = {
    "technical_failure": dict(recoverable=True, action="RETRY_PAYMENT", base_success_rate=0.85),
    "timeout": dict(recoverable=True, action="RETRY_PAYMENT", base_success_rate=0.80),
    "insufficient_funds": dict(recoverable=True, action="RETRY_LATER", base_success_rate=0.45),
    "authentication_failure": dict(recoverable=True, action="RETRY_ALT_METHOD", base_success_rate=0.55),
    "issuer_declined": dict(recoverable=True, action="RETRY_ALT_METHOD", base_success_rate=0.20),
    "risk_block": dict(recoverable=False, action="MANUAL_REVIEW", base_success_rate=0.0),
    "expired": dict(recoverable=False, action="REQUEST_CUSTOMER_ACTION", base_success_rate=0.0),
}


@dataclass
class RecoverySignals:
    payment_id: str
    status: str | None
    failure_reason: str | None
    known_category: bool
    is_recoverable_category: bool
    default_action: str
    base_success_rate: float
    has_alternate_success: bool       # another payment on the SAME order already succeeded
    has_prior_failed_attempts: bool    # other failed payments already exist on this order
    evidence: list[str] = field(default_factory=list)


def compute_recovery_signals(graph: GraphRepository, payment_id: str) -> RecoverySignals:
    payment = graph.get_node(payment_id)
    evidence = [payment_id]
    status = payment.properties.get("status") if payment else None
    failure_reason = payment.properties.get("failure_reason") if payment else None
    spec = FAILURE_TAXONOMY.get(failure_reason)

    has_alternate_success = False
    has_prior_failed = False
    order_edges = graph.edges_from(payment_id, "belongs_to")
    if order_edges:
        order_id = order_edges[0].object_id
        evidence.append(order_id)
        siblings = [e.subject_id for e in graph.edges_to(order_id, "belongs_to") if e.subject_id != payment_id]
        for sib_id in siblings:
            sib = graph.get_node(sib_id)
            if not sib:
                continue
            evidence.append(sib_id)
            if sib.properties.get("status") == "success":
                has_alternate_success = True
            elif sib.properties.get("status") == "failed":
                has_prior_failed = True

    return RecoverySignals(
        payment_id=payment_id, status=status, failure_reason=failure_reason, known_category=spec is not None,
        is_recoverable_category=spec["recoverable"] if spec else False,
        default_action=spec["action"] if spec else "MANUAL_REVIEW",
        base_success_rate=spec["base_success_rate"] if spec else 0.0,
        has_alternate_success=has_alternate_success, has_prior_failed_attempts=has_prior_failed,
        evidence=evidence,
    )
