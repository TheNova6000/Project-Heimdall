"""Ingests fees.csv -> normalized Fee records."""
from __future__ import annotations

from pathlib import Path

from financial_system.financial_state.models import Fee
from financial_system.financial_state.store import DuplicateRecordError, FinancialStateStore
from financial_system.ingestion.base import IngestionReport, make_provenance, parse_decimal, read_csv_rows


def ingest_fees(store: FinancialStateStore, raw_dir: Path, run_id: str) -> IngestionReport:
    source_file = "fees.csv"
    report = IngestionReport(source_file)
    for row_number, row in read_csv_rows(raw_dir / source_file):
        report.rows_read += 1
        rid = row.get("fee_id", "")
        try:
            if not rid or not row.get("fee_amount") or not row.get("tax_amount"):
                raise ValueError("missing required field")
            payment_id = row.get("payment_id")
            if not payment_id or not store.exists("payments", "payment_id", payment_id):
                raise ValueError(f"unknown payment_id {payment_id!r}")
            f = Fee(
                fee_id=rid, payment_id=payment_id, fee_amount=parse_decimal(row["fee_amount"]),
                tax_amount=parse_decimal(row["tax_amount"]), fee_type=row.get("fee_type", ""),
                provenance=make_provenance(source_file, rid, row_number, run_id),
            )
            store.add_fee(f)
            report.normalized += 1
        except (ValueError, DuplicateRecordError) as e:
            report.add_reject(row_number, rid, str(e))
    return report
