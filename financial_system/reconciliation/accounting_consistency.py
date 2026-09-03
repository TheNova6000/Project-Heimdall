"""
Accounting consistency check -- the "B-lite" step
FINANCIAL_ACCOUNTING_BOUNDARY_REVIEW.md's recommendation named precisely:
exactly two internal-consistency invariants a Settlement's own stored
fields already carry enough information to check, closed without
introducing a ledger, an Account entity, or any posting model.

    gross_amount - fee_amount - tax_amount == net_amount   (NET_AMOUNT_MISMATCH)
    sum(DISTINCT linked Payment.amount) == gross_amount     (PAYMENT_SUM_MISMATCH)

Deliberately standalone: NOT called from reconcile_settlement() or
run_controller_for_settlement(). This is evidence, not a decision input --
Controller's decision/decision_score/proposed_action and Phase 5's proven
607/610 baseline are completely unaffected by this module existing, since
nothing in reconciliation/controller.py or reconciliation/deterministic.py
imports it.

Reads FinancialStateStore directly, not the graph -- Settlement's graph
node (financial_graph/builder.py::_build_nodes) only carries net_amount
and settlement_date; gross/fee/tax never made it into graph properties.
Adding them there would touch shared infrastructure many other things
read; reading state directly avoids that entirely, for a check this
narrow.

Duplicate settlement_payments lines (settlement_payments.csv has no PK on
(settlement_id, payment_id) by design -- a repeated pair is a real fact
about the source, reconcile_settlement()'s own docstring) are counted
ONCE per distinct payment_id here -- confirmed empirically against every
duplicate_record-labeled settlement in reconciliation_labels.csv:
gross_amount matches sum(DISTINCT linked payments), never sum-with-
duplicates-counted-twice. Counting duplicates literally would misfire a
PAYMENT_SUM_MISMATCH on every one of those 19 already-explained cases.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from financial_system.financial_state.store import FinancialStateStore

TOLERANCE = Decimal("1.00")  # matches reconciliation/deterministic.py's own RECONCILE_TOLERANCE

NET_AMOUNT_MISMATCH = "NET_AMOUNT_MISMATCH"
PAYMENT_SUM_MISMATCH = "PAYMENT_SUM_MISMATCH"


@dataclass
class AccountingConsistencyResult:
    settlement_id: str
    status: str  # "PASS" | "EXCEPTION"
    exceptions: list[str] = field(default_factory=list)
    gross_amount: Decimal | None = None
    fee_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    net_amount: Decimal | None = None
    computed_net: Decimal | None = None            # gross - fee - tax
    net_amount_difference: Decimal | None = None    # net - computed_net
    payment_sum: Decimal | None = None               # sum of DISTINCT linked payments
    payment_sum_difference: Decimal | None = None    # gross - payment_sum
    duplicate_payment_ids: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    note: str = ""


def check_accounting_consistency(state: FinancialStateStore, settlement_id: str) -> AccountingConsistencyResult:
    settlement_row = next((dict(r) for r in state.all_rows("settlements")
                            if dict(r)["settlement_id"] == settlement_id), None)
    if settlement_row is None:
        return AccountingConsistencyResult(
            settlement_id=settlement_id, status="EXCEPTION", exceptions=["SETTLEMENT_NOT_FOUND"],
            note=f"{settlement_id} not found in financial state",
        )

    gross = Decimal(settlement_row["gross_amount"])
    fee = Decimal(settlement_row["fee_amount"])
    tax = Decimal(settlement_row["tax_amount"])
    net = Decimal(settlement_row["net_amount"])
    computed_net = gross - fee - tax
    net_diff = net - computed_net

    links = [dict(r) for r in state.all_rows("settlement_payments")
             if dict(r)["settlement_id"] == settlement_id]
    seen: set[str] = set()
    distinct_payment_ids: list[str] = []
    duplicate_payment_ids: list[str] = []
    for link in links:
        pid = link["payment_id"]
        if pid in seen:
            duplicate_payment_ids.append(pid)
            continue
        seen.add(pid)
        distinct_payment_ids.append(pid)

    payment_rows = {dict(r)["payment_id"]: dict(r) for r in state.all_rows("payments")}
    payment_sum = sum(
        (Decimal(payment_rows[pid]["amount"]) for pid in distinct_payment_ids if pid in payment_rows),
        Decimal("0"),
    )
    payment_sum_diff = gross - payment_sum

    exceptions: list[str] = []
    if abs(net_diff) > TOLERANCE:
        exceptions.append(NET_AMOUNT_MISMATCH)
    if abs(payment_sum_diff) > TOLERANCE:
        exceptions.append(PAYMENT_SUM_MISMATCH)

    return AccountingConsistencyResult(
        settlement_id=settlement_id, status="EXCEPTION" if exceptions else "PASS", exceptions=exceptions,
        gross_amount=gross, fee_amount=fee, tax_amount=tax, net_amount=net, computed_net=computed_net,
        net_amount_difference=net_diff, payment_sum=payment_sum, payment_sum_difference=payment_sum_diff,
        duplicate_payment_ids=duplicate_payment_ids, evidence=[settlement_id] + distinct_payment_ids,
    )
