"""Ingests refunds.csv -> normalized Refund records."""
from __future__ import annotations

from pathlib import Path

from financial_system.financial_state.models import Refund
from financial_system.financial_state.store import DuplicateRecordError, FinancialStateStore
from financial_system.ingestion.base import (
    IngestionReport, make_provenance, parse_decimal, parse_optional_dt, read_csv_rows,
)


def ingest_refunds(store: FinancialStateStore, raw_dir: Path, run_id: str) -> IngestionReport:
    source_file = "refunds.csv"
    report = IngestionReport(source_file)
    for row_number, row in read_csv_rows(raw_dir / source_file):
        report.rows_read += 1
        rid = row.get("refund_id", "")
        try:
            if not rid or not row.get("amount") or not row.get("created_at"):
                raise ValueError("missing required field")
            payment_id = row.get("payment_id")
            if not payment_id or not store.exists("payments", "payment_id", payment_id):
                raise ValueError(f"unknown payment_id {payment_id!r}")
            r = Refund(
                refund_id=rid, payment_id=payment_id, amount=parse_decimal(row["amount"]),
                reason=row.get("reason", ""), created_at=parse_optional_dt(row["created_at"]),
                provenance=make_provenance(source_file, rid, row_number, run_id),
            )
            store.add_refund(r)
            report.normalized += 1
        except (ValueError, DuplicateRecordError) as e:
            report.add_reject(row_number, rid, str(e))
    return report
