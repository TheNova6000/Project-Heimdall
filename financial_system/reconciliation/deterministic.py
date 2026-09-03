"""
The one place settlement-level reconciliation arithmetic lives. Moved out of
discovery_adapter/investigate.py (Phase 4's home for it, out of necessity --
Controller didn't exist yet) so Controller owns "what actually happened" and
discovery_adapter stays purely the investigation boundary. Both
discovery_adapter (for standalone testing -- open_investigation() still runs
this itself) and Controller (the real Phase 5 pipeline) call this; one
canonical implementation, not two.

Zero LLM. The only case-general deterministic explanation this looks for is
an exact duplicate line item under a settlement's `contains` edges -- a
standard reconciliation technique, not overfit to any one anomaly's
mechanics.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from financial_system.financial_graph.queries import reconciliation_neighborhood
from financial_system.financial_graph.repository import GraphRepository

RECONCILE_TOLERANCE = Decimal("1.00")


@dataclass
class ReconciliationFact:
    settlement_id: str
    status: str  # "EXPLAINED" | "PARTIALLY_EXPLAINED" | "UNEXPLAINED"
    had_raw_discrepancy: bool = False   # True if |expected-actual| > tolerance before adjustment
    duplicate_adjustment: Decimal = Decimal("0")
    expected_amount: Decimal | None = None
    actual_amount: Decimal | None = None
    unexplained_amount: Decimal | None = None
    facts: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    note: str = ""


def reconcile_settlement(graph: GraphRepository, settlement_id: str) -> ReconciliationFact:
    facts_raw = reconciliation_neighborhood(graph, "Settlement", settlement_id)
    fact_lines = [f["summary"] for f in facts_raw]
    evidence_ids = [f["node_id"] for f in facts_raw]

    settlement = graph.get_node(settlement_id)
    if not settlement:
        return ReconciliationFact(settlement_id=settlement_id, status="UNEXPLAINED",
                                   note=f"{settlement_id} not found in the graph")

    expected = Decimal(settlement.properties["net_amount"])
    bank_edges = graph.edges_from(settlement_id, "deposited_as")
    if not bank_edges:
        return ReconciliationFact(
            settlement_id=settlement_id, status="UNEXPLAINED", expected_amount=expected,
            facts=fact_lines, evidence=evidence_ids,
            note="no resolved bank transaction -- nothing to reconcile against yet",
        )
    actual = sum((Decimal(graph.get_node(e.object_id).properties["amount"]) for e in bank_edges), Decimal("0"))
    difference = expected - actual
    had_raw_discrepancy = abs(difference) > RECONCILE_TOLERANCE

    # General duplicate-line-item check: does any payment appear more than once
    # under this settlement's `contains` edges? A repeated occurrence is a
    # legitimate, case-general explanation for an overstated expected total.
    contains_edges = graph.edges_from(settlement_id, "contains")
    payment_counts = Counter(e.object_id for e in contains_edges)
    duplicate_adjustment = Decimal("0")
    for payment_id, count in payment_counts.items():
        if count > 1:
            payment = graph.get_node(payment_id)
            duplicate_adjustment += Decimal(payment.properties["amount"]) * (count - 1)

    unexplained = difference - duplicate_adjustment
    if not had_raw_discrepancy:
        status = "EXPLAINED"
    elif abs(unexplained) <= RECONCILE_TOLERANCE:
        status = "EXPLAINED"
    elif duplicate_adjustment != 0:
        status = "PARTIALLY_EXPLAINED"
    else:
        status = "UNEXPLAINED"

    return ReconciliationFact(
        settlement_id=settlement_id, status=status, had_raw_discrepancy=had_raw_discrepancy,
        duplicate_adjustment=duplicate_adjustment, expected_amount=expected, actual_amount=actual,
        unexplained_amount=unexplained, facts=fact_lines, evidence=evidence_ids,
    )
