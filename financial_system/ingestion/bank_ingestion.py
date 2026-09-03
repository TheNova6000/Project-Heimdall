"""
Ingests bank_transactions.csv -> normalized BankTransaction records.

Deliberately does NOT resolve bank_txn -> settlement_id here (no such column
exists in the raw source -- that link is only recoverable from the free-text
`description` field, sometimes cleanly, sometimes not). That resolution is
Phase 2's job (entity_resolution/), not ingestion's; this agent only
normalizes what the source actually states.
"""
from __future__ import annotations

from pathlib import Path

from financial_system.financial_state.models import BankTransaction
from financial_system.financial_state.store import DuplicateRecordError, FinancialStateStore
from financial_system.ingestion.base import (
    IngestionReport, make_provenance, parse_decimal, parse_optional_dt, read_csv_rows,
)


def ingest_bank_transactions(store: FinancialStateStore, raw_dir: Path, run_id: str) -> IngestionReport:
    source_file = "bank_transactions.csv"
    report = IngestionReport(source_file)
    for row_number, row in read_csv_rows(raw_dir / source_file):
        report.rows_read += 1
        rid = row.get("bank_txn_id", "")
        try:
            if not rid or not row.get("amount") or not row.get("value_date"):
                raise ValueError("missing required field")
            b = BankTransaction(
                bank_txn_id=rid, utr=row.get("utr", ""), amount=parse_decimal(row["amount"]),
                value_date=parse_optional_dt(row["value_date"]), description=row.get("description", ""),
                provenance=make_provenance(source_file, rid, row_number, run_id),
            )
            store.add_bank_transaction(b)
            report.normalized += 1
        except (ValueError, DuplicateRecordError) as e:
            report.add_reject(row_number, rid, str(e))
    return report
