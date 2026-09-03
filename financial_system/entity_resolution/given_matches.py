"""
Build-order steps 1-5: relationships already given directly by the source
data (Payment<->Order, Payment<->Customer, Payment<->Device/Instrument,
Settlement<->Payment). Nothing to resolve -- ingestion's foreign-key checks
already proved these hold (Phase 1). This module just materializes them as
EntityMatch records so Phase 3 can write every relationship through the same
uniform representation, and so "reference-key validation" (step 1) is a real,
re-run-able check rather than an assumption carried over from Phase 1.
"""
from __future__ import annotations

from financial_system.entity_resolution.models import EntityMatch
from financial_system.financial_state.store import FinancialStateStore


def validate_reference_keys(store: FinancialStateStore) -> list[str]:
    """Step 1. Re-proves every FK Phase 1 accepted still resolves against the
    reference tables. Returns a list of violation strings; empty = clean."""
    violations = []
    checks = [
        ("payments", "order_id", "orders", "order_id"),
        ("payments", "customer_id", "customers", "customer_id"),
        ("payments", "merchant_id", "merchants", "merchant_id"),
        ("payments", "device_id", "devices", "device_id"),
        ("payments", "instrument_id", "payment_instruments", "instrument_id"),
        ("orders", "merchant_id", "merchants", "merchant_id"),
        ("orders", "customer_id", "customers", "customer_id"),
        ("settlements", "merchant_id", "merchants", "merchant_id"),
        ("settlement_payments", "settlement_id", "settlements", "settlement_id"),
        ("settlement_payments", "payment_id", "payments", "payment_id"),
    ]
    for table, fk_col, ref_table, ref_col in checks:
        for row in store.all_rows(table):
            fk_value = row[fk_col]
            if not store.exists(ref_table, ref_col, fk_value):
                violations.append(f"{table}.{fk_col}={fk_value!r} has no matching {ref_table}.{ref_col}")
    return violations


def resolve_given_matches(store: FinancialStateStore) -> list[EntityMatch]:
    """Steps 2-5: materialize the already-given relationships as EntityMatch
    records, confidence 1.0, method='foreign_key'."""
    matches: list[EntityMatch] = []

    for row in store.all_rows("payments"):
        pid = row["payment_id"]
        matches.append(EntityMatch(
            subject_type="Payment", subject_id=pid, object_type="Order", object_id=row["order_id"],
            relation="belongs_to", match_method="foreign_key", match_score=1.0,
            match_evidence=["payments.order_id given directly by source"],
            source_record_ids=[pid, row["order_id"]],
        ))
        matches.append(EntityMatch(
            subject_type="Payment", subject_id=pid, object_type="Customer", object_id=row["customer_id"],
            relation="initiated_by", match_method="foreign_key", match_score=1.0,
            match_evidence=["payments.customer_id given directly by source"],
            source_record_ids=[pid, row["customer_id"]],
        ))
        matches.append(EntityMatch(
            subject_type="Payment", subject_id=pid, object_type="Device", object_id=row["device_id"],
            relation="used_device", match_method="foreign_key", match_score=1.0,
            match_evidence=["payments.device_id given directly by source"],
            source_record_ids=[pid, row["device_id"]],
        ))
        matches.append(EntityMatch(
            subject_type="Payment", subject_id=pid, object_type="PaymentInstrument",
            object_id=row["instrument_id"], relation="used_instrument", match_method="foreign_key",
            match_score=1.0, match_evidence=["payments.instrument_id given directly by source"],
            source_record_ids=[pid, row["instrument_id"]],
        ))

    # settlement_payments is a junction with no synthetic id -- a repeated pair
    # (duplicate_record anomaly, see DATASET_DESIGN.md) yields two distinct
    # EntityMatch records here, preserved exactly as Phase 1 preserved them.
    for row in store.all_rows("settlement_payments"):
        matches.append(EntityMatch(
            subject_type="Payment", subject_id=row["payment_id"],
            object_type="Settlement", object_id=row["settlement_id"],
            relation="settles_into", match_method="foreign_key", match_score=1.0,
            match_evidence=["settlement_payments row given directly by source"],
            source_record_ids=[row["payment_id"], row["settlement_id"]],
        ))

    return matches
