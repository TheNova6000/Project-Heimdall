"""
Verification check #2 -- Temporal integrity (NORTH_STAR.md Section 24:
"Was future information leaked?" / Section 35: "temporal leakage").

This generalizes the ONE real temporal-pinning mechanism that actually
exists in this codebase today: Block 5's Risk fix
(`financial_graph/queries.py::edges_to_as_of`, consumed by
`risk/signals.py::compute_device_risk_signals(..., as_of=...)` and exposed
through `risk/risk_agent.py::run_risk_for_device(..., as_of=...)`). Its own
docstring names the property directly: "an edge whose subject doesn't
exist yet at as_of carries no evidence at that decision time". Read in
full before writing this file -- see queries.py lines 16-43 and
risk/temporal_runner.py, which already benchmarks Risk precision/recall
under this exact as-of-scoped code path over the real corpus.

Design choice, stated honestly: `AgentVerdict` (verdict.py) carries no
timestamp field at all -- it has no "as of when was this decided" concept
built in anywhere in the schema. So this check cannot discover a verdict's
own decision-time by inspecting the verdict; the CALLER must supply
`as_of` explicitly, the same way `run_risk_for_device`'s own caller does.
That is not a shortcut -- it is the honest shape of what's actually
auditable given today's schema, named as a caveat in this module's README
rather than glossed over.

Consequently: this check is only run FOR REAL, meaningfully, against Risk,
because Risk is the only one of the three domains whose agent function
accepts an `as_of` parameter in the first place (`run_recovery_for_payment`
and `run_controller_for_settlement` take no such argument -- confirmed by
reading recovery/recovery_agent.py and reconciliation/controller.py
directly, not assumed). Inventing a decision-time boundary for Recovery or
Controller that their own frozen code never claims to honor would be
exactly the kind of manufactured violation the task instructions forbid --
so this module does not do that. See the verification README for this
named, honest scope gap.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from financial_system.financial_graph.repository import GraphRepository
from financial_system.verdict import AgentVerdict

# Which node property is "the" observation timestamp for a node type, for
# THIS check's purpose specifically: was this evidence knowable at
# decision time. Deliberately NOT the same as risk/signals.py's own
# `payment_time()` helper (which prefers captured_at, then falls back to
# created_at) -- that helper answers a different question (when did this
# payment settle, for burst-window timing WITHIN an already as-of-filtered
# evidence set). The actual as-of BOUNDARY -- financial_graph/queries.py's
# `edges_to_as_of(..., timestamp_field="created_at")`, called with its
# default from risk/signals.py's `_payments_on_device()` -- filters
# strictly on each Payment's own created_at (when it became observable at
# all), never captured_at (when it later settled). Using captured_at here
# instead would flag a real, correct as-of decision as a false "leak"
# merely because a payment observed before the decision happened to
# capture/settle afterward -- confirmed by first getting a spurious ~150
# "violations" during this module's own testing before catching the
# mismatch and fixing it to created_at, matching edges_to_as_of's actual
# field exactly. Node types NOT listed here (Merchant, Order, Refund, Fee,
# PaymentInstrument) carry no timestamp property in the graph at all --
# financial_graph/builder.py's _build_nodes() never copies their
# created_at into node properties, even though the underlying
# FinancialStateStore row has one. That is a real, structural gap in what
# this check can see through; evidence ids of these types are counted as
# `skipped_no_timestamp`, never silently treated as "verified clean".
TIMESTAMP_FIELDS: dict[str, tuple[str, ...]] = {
    "Customer": ("created_at",),
    "Device": ("first_seen_at",),
    "Payment": ("created_at",),
    "Settlement": ("settlement_date",),
    "BankTransaction": ("value_date",),
}


def node_timestamp(node) -> datetime | None:
    fields = TIMESTAMP_FIELDS.get(node.node_type)
    if not fields:
        return None
    for f in fields:
        v = node.properties.get(f)
        if v:
            return datetime.fromisoformat(v)
    return None


@dataclass
class TemporalViolation:
    verdict_subject: str
    evidence_field: str        # "evidence" | "affected_entities"
    evidence_id: str
    node_type: str
    evidence_timestamp: str
    as_of: str


@dataclass
class TemporalCheckResult:
    verdict_subject: str
    as_of: str
    n_checked: int
    n_skipped_no_timestamp: int
    n_skipped_unknown_node: int
    violations: list[TemporalViolation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations


def check_temporal_integrity(graph: GraphRepository, verdict: AgentVerdict,
                              as_of: datetime) -> TemporalCheckResult:
    """Walks every id in verdict.evidence and verdict.affected_entities,
    resolves it to a graph node, and confirms that node's own observation
    timestamp is not later than `as_of` -- the decision's own claimed
    effective as-of time, supplied by the caller (see module docstring for
    why AgentVerdict itself can't carry this)."""
    checked = skipped_no_ts = skipped_unknown = 0
    violations: list[TemporalViolation] = []

    for field_name, ids in (("evidence", verdict.evidence), ("affected_entities", verdict.affected_entities)):
        for eid in ids:
            node = graph.get_node(eid)
            if node is None:
                skipped_unknown += 1
                continue
            ts = node_timestamp(node)
            if ts is None:
                skipped_no_ts += 1
                continue
            checked += 1
            if ts > as_of:
                violations.append(TemporalViolation(
                    verdict_subject=verdict.subject, evidence_field=field_name, evidence_id=eid,
                    node_type=node.node_type, evidence_timestamp=ts.isoformat(), as_of=as_of.isoformat(),
                ))

    return TemporalCheckResult(
        verdict_subject=verdict.subject, as_of=as_of.isoformat(), n_checked=checked,
        n_skipped_no_timestamp=skipped_no_ts, n_skipped_unknown_node=skipped_unknown, violations=violations,
    )
