"""
Normalized financial state models. One class per entity in data/raw/.

Every model carries a `provenance` field so any downstream layer (graph,
investigation) can always answer "what source record is this from" -- this is
the mechanism Phase 1's invariant depends on.

Money fields are Decimal, parsed directly from the CSV string. Never route a
monetary value through float (Rules.md).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class Provenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_file: str          # e.g. "payments.csv"
    source_record_id: str     # the row's natural id in the source file
    row_number: int           # 1-indexed, excluding header
    ingestion_run_id: str
    ingested_at: datetime


class Merchant(BaseModel):
    merchant_id: str
    name: str
    category: str
    created_at: datetime
    provenance: Provenance


class Customer(BaseModel):
    customer_id: str
    name: str
    email: str
    created_at: datetime
    provenance: Provenance


class Device(BaseModel):
    device_id: str
    fingerprint: str
    first_seen_at: datetime
    provenance: Provenance


class PaymentInstrument(BaseModel):
    instrument_id: str
    type: str
    masked_identifier: str
    customer_id: str
    provenance: Provenance


class Order(BaseModel):
    order_id: str
    merchant_id: str
    customer_id: str
    amount: Decimal
    currency: str
    created_at: datetime
    provenance: Provenance


class Payment(BaseModel):
    payment_id: str
    order_id: str
    customer_id: str
    merchant_id: str
    device_id: str
    instrument_id: str
    amount: Decimal
    currency: str
    status: str                          # "success" | "failed"
    failure_reason: Optional[str] = None
    created_at: datetime
    authorized_at: Optional[datetime] = None
    captured_at: Optional[datetime] = None
    provenance: Provenance


class Refund(BaseModel):
    refund_id: str
    payment_id: str
    amount: Decimal
    reason: str
    created_at: datetime
    provenance: Provenance


class Fee(BaseModel):
    fee_id: str
    payment_id: str
    fee_amount: Decimal
    tax_amount: Decimal
    fee_type: str
    provenance: Provenance


class Settlement(BaseModel):
    settlement_id: str
    merchant_id: str
    settlement_date: datetime
    gross_amount: Decimal
    fee_amount: Decimal
    tax_amount: Decimal
    net_amount: Decimal
    provenance: Provenance


class SettlementPayment(BaseModel):
    """Junction row. No synthetic id -- (settlement_id, payment_id) pairs are
    NOT deduplicated at ingestion; a repeated pair in the source is a real fact
    about the source (e.g. a duplicate-record reconciliation anomaly) and must
    survive ingestion unchanged, not get silently collapsed."""
    settlement_id: str
    payment_id: str
    provenance: Provenance


class BankTransaction(BaseModel):
    bank_txn_id: str
    utr: str
    amount: Decimal
    value_date: datetime
    description: str
    provenance: Provenance
