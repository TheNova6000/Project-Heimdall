"""Ingests payments.csv -> normalized Payment records."""
from __future__ import annotations

from pathlib import Path

from financial_system.financial_state.models import Payment
from financial_system.financial_state.store import DuplicateRecordError, FinancialStateStore
from financial_system.ingestion.base import (
    IngestionReport, make_provenance, parse_decimal, parse_optional_dt, read_csv_rows,
)

_VALID_STATUS = {"success", "failed"}
_FK_TABLES = [
    ("order_id", "orders", "order_id"),
    ("customer_id", "customers", "customer_id"),
    ("merchant_id", "merchants", "merchant_id"),
    ("device_id", "devices", "device_id"),
    ("instrument_id", "payment_instruments", "instrument_id"),
]


def ingest_payments(store: FinancialStateStore, raw_dir: Path, run_id: str) -> IngestionReport:
    source_file = "payments.csv"
    report = IngestionReport(source_file)
    for row_number, row in read_csv_rows(raw_dir / source_file):
        report.rows_read += 1
        rid = row.get("payment_id", "")
        try:
            if not rid or not row.get("amount") or not row.get("created_at"):
                raise ValueError("missing required field")
            status = row.get("status", "")
            if status not in _VALID_STATUS:
                raise ValueError(f"invalid status {status!r}")
            if status == "failed" and not row.get("failure_reason"):
                raise ValueError("failed payment missing failure_reason")
            for field_name, table, column in _FK_TABLES:
                fk = row.get(field_name)
                if not fk or not store.exists(table, column, fk):
                    raise ValueError(f"unknown {field_name} {fk!r}")

            p = Payment(
                payment_id=rid, order_id=row["order_id"], customer_id=row["customer_id"],
                merchant_id=row["merchant_id"], device_id=row["device_id"],
                instrument_id=row["instrument_id"], amount=parse_decimal(row["amount"]),
                currency=row.get("currency", "INR"), status=status,
                failure_reason=row.get("failure_reason") or None,
                created_at=parse_optional_dt(row["created_at"]),
                authorized_at=parse_optional_dt(row.get("authorized_at", "")),
                captured_at=parse_optional_dt(row.get("captured_at", "")),
                provenance=make_provenance(source_file, rid, row_number, run_id),
            )
            store.add_payment(p)
            report.normalized += 1
        except (ValueError, DuplicateRecordError) as e:
            report.add_reject(row_number, rid, str(e))
    return report
