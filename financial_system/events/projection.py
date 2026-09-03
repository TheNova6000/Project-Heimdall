"""
Stage 1/2 projection (MIGRATION_DESIGN.md §6): replays the Event Store back
into a FinancialStateStore's transactional tables. Reference tables
(merchants/customers/devices/instruments) are NOT projected here -- they
stay on the unchanged Phase 1 reference_ingestion.py path (backfill.py's
own scope decision); this module needs them already populated in the
target store to satisfy foreign-key checks.

Reconstructs Provenance from the event's own source/source_event_id
(`source="csv_backfill:payments.csv"`, `source_event_id="row_12""`) rather
than anything carried in the payload -- see backfill.py.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from financial_system.events.store import EventStore
from financial_system.financial_state.models import (
    BankTransaction, Fee, Order, Payment, Provenance, Refund, Settlement, SettlementPayment,
)
from financial_system.financial_state.store import FinancialStateStore


def _provenance(event, run_id: str) -> Provenance:
    source_file = event.source.split(":", 1)[1] if ":" in event.source else event.source
    # source_event_id is "row_{N}_{event_type}" (backfill.py) -- the row number is
    # always the second underscore-delimited token, regardless of event_type's own
    # underscores/casing, since it's inserted immediately after the literal "row".
    row_number = int(event.source_event_id.split("_")[1]) if event.source_event_id else 0
    return Provenance(
        source_file=source_file, source_record_id=event.subject_id, row_number=row_number,
        ingestion_run_id=run_id, ingested_at=event.recorded_at,
    )


def project(events: EventStore, target: FinancialStateStore, as_of: datetime | None = None) -> dict[str, int]:
    """as_of, when given, reconstructs state as it existed at that instant:
    only events with occurred_at <= as_of are considered, and every merge
    below (terminal outcome, retry override) is restricted to that filtered
    set -- so an as_of before a retry's occurred_at yields the pre-retry
    state even though the full log already contains the retry. Omitting
    as_of (the default) is byte-identical to projecting the full log, i.e.
    "now"; one function, parameterized by time, not two code paths."""
    run_id = f"projected_{uuid.uuid4().hex[:12]}"
    counts: dict[str, int] = {}

    def bump(name):
        counts[name] = counts.get(name, 0) + 1

    # -- Orders --
    for e in events.all_events("OrderCreated", as_of=as_of):
        p = e.payload
        target.add_order(Order(
            order_id=p["order_id"], merchant_id=p["merchant_id"], customer_id=p["customer_id"],
            amount=Decimal(p["amount"]), currency=p["currency"],
            created_at=datetime.fromisoformat(p["created_at"]), provenance=_provenance(e, run_id),
        ))
        bump("orders")

    # -- Payments: merge PaymentCreated + (PaymentCaptured | PaymentFailed) by subject_id,
    # then fold in the latest qualifying ActionOutcomeObserved(SUCCESS, RETRY*) as a
    # later-in-time override on status/failure_reason/captured_at. This is the same
    # fact Stage 4's apply_payment_retry_success() applies via an in-place UPDATE against
    # live state -- folding it in here too means a from-scratch replay of the event log
    # (this function) agrees with the live incremental path, and is what makes as_of
    # actually reflect a retry that succeeded before T rather than only the original
    # terminal event. --
    created_by_payment: dict[str, object] = {e.subject_id: e for e in events.all_events("PaymentCreated", as_of=as_of)}
    terminal_by_payment: dict[str, object] = {}
    for e in events.all_events("PaymentCaptured", as_of=as_of):
        terminal_by_payment[e.subject_id] = e
    for e in events.all_events("PaymentFailed", as_of=as_of):
        terminal_by_payment[e.subject_id] = e

    retry_override_by_payment: dict[str, object] = {}
    for e in events.all_events("ActionOutcomeObserved", as_of=as_of):
        p = e.payload
        if p.get("verification_result") != "SUCCESS" or not str(p.get("action_taken", "")).startswith("RETRY"):
            continue
        existing = retry_override_by_payment.get(e.subject_id)
        if existing is None or e.occurred_at > existing.occurred_at:
            retry_override_by_payment[e.subject_id] = e

    for payment_id, created in created_by_payment.items():
        terminal = terminal_by_payment.get(payment_id)
        override = retry_override_by_payment.get(payment_id)
        cp, tp = created.payload, (terminal.payload if terminal else {})
        status = tp.get("status", "failed")
        failure_reason = tp.get("failure_reason") or None
        captured_at = datetime.fromisoformat(tp["captured_at"]) if tp.get("captured_at") else None
        if override is not None:
            status, failure_reason, captured_at = "success", None, override.occurred_at
        target.add_payment(Payment(
            payment_id=payment_id, order_id=cp["order_id"], customer_id=cp["customer_id"],
            merchant_id=cp["merchant_id"], device_id=cp["device_id"], instrument_id=cp["instrument_id"],
            amount=Decimal(cp["amount"]), currency=cp["currency"],
            status=status, failure_reason=failure_reason,
            created_at=datetime.fromisoformat(cp["created_at"]),
            authorized_at=datetime.fromisoformat(tp["authorized_at"]) if tp.get("authorized_at") else None,
            captured_at=captured_at,
            # Provenance always traces to the original terminal event (or creation),
            # never to a retry override -- Provenance means "which source record",
            # not "what is the latest fact"; the latter lives in the event log itself,
            # queryable via events_for_subject(), not flattened into this one field.
            provenance=_provenance(terminal or created, run_id),
        ))
        bump("payments")

    # -- Settlements + SettlementPayment junction rows (from payload["payment_ids"], preserves duplicates) --
    for e in events.all_events("SettlementReceived", as_of=as_of):
        p = e.payload
        target.add_settlement(Settlement(
            settlement_id=p["settlement_id"], merchant_id=p["merchant_id"],
            settlement_date=datetime.fromisoformat(p["settlement_date"]),
            gross_amount=Decimal(p["gross_amount"]), fee_amount=Decimal(p["fee_amount"]),
            tax_amount=Decimal(p["tax_amount"]), net_amount=Decimal(p["net_amount"]),
            provenance=_provenance(e, run_id),
        ))
        bump("settlements")
        for link in p["payment_links"]:
            # A link's provenance is its OWN row in settlement_payments.csv, not its
            # parent settlement's -- matches the composite id
            # ingest_settlement_payments() uses directly, not derived from the event.
            link_provenance = Provenance(
                source_file="settlement_payments.csv",
                source_record_id=f"{p['settlement_id']}:{link['payment_id']}:row{link['row_number']}",
                row_number=link["row_number"], ingestion_run_id=run_id, ingested_at=e.recorded_at,
            )
            target.add_settlement_payment(SettlementPayment(
                settlement_id=p["settlement_id"], payment_id=link["payment_id"],
                provenance=link_provenance,
            ))
            bump("settlement_payments")

    # -- Bank transactions --
    for e in events.all_events("BankTransactionRecorded", as_of=as_of):
        p = e.payload
        target.add_bank_transaction(BankTransaction(
            bank_txn_id=p["bank_txn_id"], utr=p["utr"], amount=Decimal(p["amount"]),
            value_date=datetime.fromisoformat(p["value_date"]), description=p["description"],
            provenance=_provenance(e, run_id),
        ))
        bump("bank_transactions")

    # -- Refunds --
    for e in events.all_events("RefundRecorded", as_of=as_of):
        p = e.payload
        target.add_refund(Refund(
            refund_id=p["refund_id"], payment_id=p["payment_id"], amount=Decimal(p["amount"]),
            reason=p["reason"], created_at=datetime.fromisoformat(p["created_at"]),
            provenance=_provenance(e, run_id),
        ))
        bump("refunds")

    # -- Fees --
    for e in events.all_events("FeeRecorded", as_of=as_of):
        p = e.payload
        target.add_fee(Fee(
            fee_id=p["fee_id"], payment_id=p["payment_id"], fee_amount=Decimal(p["fee_amount"]),
            tax_amount=Decimal(p["tax_amount"]), fee_type=p["fee_type"],
            provenance=_provenance(e, run_id),
        ))
        bump("fees")

    target.commit()
    return counts
