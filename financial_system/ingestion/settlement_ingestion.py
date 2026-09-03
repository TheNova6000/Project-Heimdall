"""
Ingests settlements.csv -> normalized Settlement records, and
settlement_payments.csv -> normalized SettlementPayment junction records.

settlement_payments.csv has no natural per-row id and may legitimately contain
a repeated (settlement_id, payment_id) pair -- that's the duplicate_record
reconciliation anomaly from data/DATASET_DESIGN.md, a fact about the source,
not an ingestion error. It is intentionally NOT deduplicated here (Rules.md:
the code adapts to the dataset, not the other way around).
"""
from __future__ import annotations

from pathlib import Path

from financial_system.financial_state.models import Settlement, SettlementPayment
from financial_system.financial_state.store import DuplicateRecordError, FinancialStateStore
from financial_system.ingestion.base import (
    IngestionReport, make_provenance, parse_decimal, parse_optional_dt, read_csv_rows,
)


def ingest_settlements(store: FinancialStateStore, raw_dir: Path, run_id: str) -> IngestionReport:
    source_file = "settlements.csv"
    report = IngestionReport(source_file)
    for row_number, row in read_csv_rows(raw_dir / source_file):
        report.rows_read += 1
        rid = row.get("settlement_id", "")
        try:
            required = ("gross_amount", "fee_amount", "tax_amount", "net_amount", "settlement_date")
            if not rid or not all(row.get(f) for f in required):
                raise ValueError("missing required field")
            if not store.exists("merchants", "merchant_id", row.get("merchant_id", "")):
                raise ValueError(f"unknown merchant_id {row.get('merchant_id')!r}")
            s = Settlement(
                settlement_id=rid, merchant_id=row["merchant_id"],
                settlement_date=parse_optional_dt(row["settlement_date"]),
                gross_amount=parse_decimal(row["gross_amount"]),
                fee_amount=parse_decimal(row["fee_amount"]),
                tax_amount=parse_decimal(row["tax_amount"]),
                net_amount=parse_decimal(row["net_amount"]),
                provenance=make_provenance(source_file, rid, row_number, run_id),
            )
            store.add_settlement(s)
            report.normalized += 1
        except (ValueError, DuplicateRecordError) as e:
            report.add_reject(row_number, rid, str(e))
    return report


def ingest_settlement_payments(store: FinancialStateStore, raw_dir: Path, run_id: str) -> IngestionReport:
    source_file = "settlement_payments.csv"
    report = IngestionReport(source_file)
    for row_number, row in read_csv_rows(raw_dir / source_file):
        report.rows_read += 1
        settlement_id = row.get("settlement_id", "")
        payment_id = row.get("payment_id", "")
        source_record_id = f"{settlement_id}:{payment_id}:row{row_number}"
        try:
            if not settlement_id or not payment_id:
                raise ValueError("missing required field")
            if not store.exists("settlements", "settlement_id", settlement_id):
                raise ValueError(f"unknown settlement_id {settlement_id!r}")
            if not store.exists("payments", "payment_id", payment_id):
                raise ValueError(f"unknown payment_id {payment_id!r}")
            sp = SettlementPayment(
                settlement_id=settlement_id, payment_id=payment_id,
                provenance=make_provenance(source_file, source_record_id, row_number, run_id),
            )
            store.add_settlement_payment(sp)
            report.normalized += 1
        except (ValueError, DuplicateRecordError) as e:
            report.add_reject(row_number, source_record_id, str(e))
    return report
