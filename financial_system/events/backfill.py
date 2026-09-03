"""
Stage 2 (MIGRATION_DESIGN.md §7): generate the events that WOULD have been
recorded had this system been event-sourced from the start, from the
existing Phase 0 raw CSVs. `recorded_at = occurred_at` for every event here
-- we have no genuine "we learned about it later" data for a historical
backfill; only real Stage 3+ events (real ActionOutcomeObserved) will have
a genuine gap.

Provenance rides on the event's own `source`/`source_event_id` fields
(`source="csv_backfill:payments.csv"`, `source_event_id="row_N"`) rather
than living in the payload -- this doubles as the dedup key that prevents
backfilling the same CSV row twice.

Scope decision, stated explicitly: reference/dimension data (Merchant,
Customer, Device, PaymentInstrument) is NOT event-sourced in this
migration -- these are standing entities, not point-in-time occurrences
(matches how even Stripe doesn't model an elaborate Customer lifecycle).
They stay on the existing Phase 1 ingestion path unchanged.
"""
from __future__ import annotations

import csv
import uuid
from datetime import datetime, timezone
from pathlib import Path

from financial_system.events.models import Event
from financial_system.events.store import EventStore

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = REPO_ROOT / "financial_system" / "data" / "raw"

SOURCE_PREFIX = "csv_backfill"


def _event(event_type: str, subject_id: str, occurred_at: str, payload: dict,
           source_file: str, row_number: int, correlation_id: str,
           causation_id: str | None = None) -> Event:
    now = datetime.now(timezone.utc)
    # One CSV row can produce more than one event (payments.csv: PaymentCreated +
    # a terminal event) -- event_type is folded into source_event_id so the
    # (source, source_event_id) dedup key stays unique per row per event, not
    # just per row.
    return Event(
        event_id=str(uuid.uuid4()), event_type=event_type, subject_id=subject_id,
        source=f"{SOURCE_PREFIX}:{source_file}", source_event_id=f"row_{row_number}_{event_type}",
        occurred_at=datetime.fromisoformat(occurred_at) if occurred_at else now,
        recorded_at=datetime.fromisoformat(occurred_at) if occurred_at else now,
        payload=payload, correlation_id=correlation_id, causation_id=causation_id,
    )


def backfill(store: EventStore, raw_dir: Path = RAW_DIR) -> dict[str, int]:
    counts: dict[str, int] = {}
    payment_created_event_id: dict[str, str] = {}   # payment_id -> event_id, for causation links
    payment_terminal_event_id: dict[str, str] = {}   # payment_id -> event_id of Captured/Failed

    def add(event: Event):
        store.append(event)
        counts[event.event_type] = counts.get(event.event_type, 0) + 1

    # -- Orders --
    with open(raw_dir / "orders.csv", newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            add(_event("OrderCreated", row["order_id"], row["created_at"],
                       {"order_id": row["order_id"], "merchant_id": row["merchant_id"],
                        "customer_id": row["customer_id"], "amount": row["amount"],
                        "currency": row["currency"], "created_at": row["created_at"]},
                       "orders.csv", i, correlation_id=row["order_id"]))

    # -- Payments: PaymentCreated always, then PaymentCaptured/PaymentFailed --
    with open(raw_dir / "payments.csv", newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            pid = row["payment_id"]
            created = _event(
                "PaymentCreated", pid, row["created_at"],
                {"payment_id": pid, "order_id": row["order_id"], "customer_id": row["customer_id"],
                 "merchant_id": row["merchant_id"], "device_id": row["device_id"],
                 "instrument_id": row["instrument_id"], "amount": row["amount"],
                 "currency": row["currency"], "created_at": row["created_at"], "attempt_number": 1},
                "payments.csv", i, correlation_id=pid,
            )
            add(created)
            payment_created_event_id[pid] = created.event_id

            if row["status"] == "success":
                terminal = _event(
                    "PaymentCaptured", pid, row["captured_at"],
                    {"status": "success", "failure_reason": "", "authorized_at": row["authorized_at"],
                     "captured_at": row["captured_at"], "attempt_number": 1},
                    "payments.csv", i, correlation_id=pid, causation_id=created.event_id,
                )
            else:
                # No distinct failure timestamp exists in the raw corpus -- documented
                # limitation, not fabricated precision. occurred_at reuses created_at.
                terminal = _event(
                    "PaymentFailed", pid, row["created_at"],
                    {"status": "failed", "failure_reason": row["failure_reason"],
                     "authorized_at": "", "captured_at": "", "attempt_number": 1},
                    "payments.csv", i, correlation_id=pid, causation_id=created.event_id,
                )
            add(terminal)
            payment_terminal_event_id[pid] = terminal.event_id

    # -- Settlements (settlement_payments.csv joined in as payload detail, not a separate
    # event -- see the taxonomy note above). Each link carries settlement_payments.csv's
    # OWN row_number, not settlements.csv's, so projection.py can reconstruct the exact
    # composite provenance id (f"{settlement_id}:{payment_id}:row{row_number}") the
    # original direct-ingestion path uses -- a link is not "the same fact" as its parent
    # settlement, so it can't inherit the parent event's provenance and still match.
    settlement_payment_links: dict[str, list[dict]] = {}
    with open(raw_dir / "settlement_payments.csv", newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            settlement_payment_links.setdefault(row["settlement_id"], []).append(
                {"payment_id": row["payment_id"], "row_number": i})

    with open(raw_dir / "settlements.csv", newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            sid = row["settlement_id"]
            add(_event(
                "SettlementReceived", sid, row["settlement_date"],
                {"settlement_id": sid, "merchant_id": row["merchant_id"],
                 "settlement_date": row["settlement_date"], "gross_amount": row["gross_amount"],
                 "fee_amount": row["fee_amount"], "tax_amount": row["tax_amount"],
                 "net_amount": row["net_amount"],
                 "payment_links": settlement_payment_links.get(sid, [])},
                "settlements.csv", i, correlation_id=sid,
            ))

    # settlement_payments.csv rows are junction facts, not independently eventful --
    # their content (including preserved duplicates, e.g. the duplicate_record
    # anomaly) already lives in SettlementReceived's payload["payment_ids"] above,
    # built from a plain list append, not a set. No separate event type for this;
    # inventing one (or reusing SettlementReceived) would misuse the taxonomy --
    # event_type describes a fact, and "a payment was linked to a settlement" isn't
    # "a settlement was received."

    # -- Bank transactions --
    with open(raw_dir / "bank_transactions.csv", newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            add(_event(
                "BankTransactionRecorded", row["bank_txn_id"], row["value_date"],
                {"bank_txn_id": row["bank_txn_id"], "utr": row["utr"], "amount": row["amount"],
                 "value_date": row["value_date"], "description": row["description"]},
                "bank_transactions.csv", i, correlation_id=row["bank_txn_id"],
            ))

    # -- Refunds --
    with open(raw_dir / "refunds.csv", newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            pid = row["payment_id"]
            add(_event(
                "RefundRecorded", row["refund_id"], row["created_at"],
                {"refund_id": row["refund_id"], "payment_id": pid, "amount": row["amount"],
                 "reason": row["reason"], "created_at": row["created_at"]},
                "refunds.csv", i, correlation_id=pid,
                causation_id=payment_terminal_event_id.get(pid),
            ))

    # -- Fees: no timestamp column exists in fees.csv -- borrow the payment's
    # captured_at as occurred_at, documented, not fabricated as if it were real. --
    payment_captured_at: dict[str, str] = {}
    with open(raw_dir / "payments.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["status"] == "success":
                payment_captured_at[row["payment_id"]] = row["captured_at"]

    with open(raw_dir / "fees.csv", newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            pid = row["payment_id"]
            add(_event(
                "FeeRecorded", row["fee_id"], payment_captured_at.get(pid),
                {"fee_id": row["fee_id"], "payment_id": pid, "fee_amount": row["fee_amount"],
                 "tax_amount": row["tax_amount"], "fee_type": row["fee_type"],
                 "_occurred_at_is_borrowed_from_payment": True},
                "fees.csv", i, correlation_id=pid,
                causation_id=payment_terminal_event_id.get(pid),
            ))

    store.commit()
    return counts
