"""
Orchestrates Phase 1: raw CSVs -> Financial State, then proves the Phase 1
invariant from Phases.md:

    every source record was ingested exactly once, normalized deterministically,
    and can be traced back to its original source record.

Run directly: `python -m financial_system.financial_state.builder`
"""
from __future__ import annotations

import csv
import sys
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from financial_system.financial_state.store import FinancialStateStore
from financial_system.ingestion import bank_ingestion, fee_ingestion, payment_ingestion
from financial_system.ingestion import reference_ingestion, refund_ingestion, settlement_ingestion

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = REPO_ROOT / "financial_system" / "data" / "raw"
DB_PATH = REPO_ROOT / "financial_system" / "data" / "financial_state.db"

# (source_file, table, id_column) -- used for the row-count invariant check.
# order matters: FK dependencies must be ingested before their dependents.
_INGESTION_STEPS = [
    ("merchants.csv", "merchants", reference_ingestion.ingest_merchants),
    ("customers.csv", "customers", reference_ingestion.ingest_customers),
    ("devices.csv", "devices", reference_ingestion.ingest_devices),
    ("payment_instruments.csv", "payment_instruments", reference_ingestion.ingest_instruments),
    ("orders.csv", "orders", reference_ingestion.ingest_orders),
    ("payments.csv", "payments", payment_ingestion.ingest_payments),
    ("refunds.csv", "refunds", refund_ingestion.ingest_refunds),
    ("fees.csv", "fees", fee_ingestion.ingest_fees),
    ("settlements.csv", "settlements", settlement_ingestion.ingest_settlements),
    ("settlement_payments.csv", "settlement_payments", settlement_ingestion.ingest_settlement_payments),
    ("bank_transactions.csv", "bank_transactions", bank_ingestion.ingest_bank_transactions),
]

# (source_file, amount_column, table, table_column) for the independent money
# checksum -- summed straight from the CSV text, bypassing all ingestion code,
# so it proves the store's total wasn't silently altered on the way in.
_MONEY_CHECKS = [
    ("payments.csv", "amount", "payments", "amount"),
    ("refunds.csv", "amount", "refunds", "amount"),
    ("fees.csv", "fee_amount", "fees", "fee_amount"),
    ("settlements.csv", "net_amount", "settlements", "net_amount"),
    ("bank_transactions.csv", "amount", "bank_transactions", "amount"),
]


@dataclass
class Phase1Result:
    passed: bool
    reports: list
    row_count_failures: list[str]
    checksum_failures: list[str]


def _raw_row_count(source_file: str) -> int:
    with open(RAW_DIR / source_file, newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def _raw_money_checksum(source_file: str, column: str) -> Decimal:
    total = Decimal("0")
    with open(RAW_DIR / source_file, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get(column):
                total += Decimal(row[column])
    return total


def build_financial_state(db_path: Path = DB_PATH, raw_dir: Path = RAW_DIR) -> tuple[FinancialStateStore, Phase1Result]:
    if db_path.exists():
        db_path.unlink()  # fresh store every run -- Phase 1 proves a clean full ingest, not incremental merge
    store = FinancialStateStore(db_path)
    run_id = f"run_{uuid.uuid4().hex[:12]}"

    reports = []
    for source_file, table, ingest_fn in _INGESTION_STEPS:
        report = ingest_fn(store, raw_dir, run_id)
        store.commit()
        reports.append(report)

    row_count_failures = []
    for source_file, table, _ in _INGESTION_STEPS:
        report = next(r for r in reports if r.source_file == source_file)
        raw_count = _raw_row_count(source_file)
        if report.rows_read != raw_count:
            row_count_failures.append(
                f"{source_file}: read {report.rows_read} rows but CSV has {raw_count}")
        if report.normalized + report.rejected != report.rows_read:
            row_count_failures.append(
                f"{source_file}: normalized({report.normalized}) + rejected({report.rejected}) "
                f"!= rows_read({report.rows_read})")
        if report.rejected:
            row_count_failures.append(
                f"{source_file}: {report.rejected} row(s) rejected -- {report.rejects[:3]}")

    checksum_failures = []
    for source_file, csv_col, table, table_col in _MONEY_CHECKS:
        expected = _raw_money_checksum(source_file, csv_col)
        actual = store.sum_decimal(table, table_col)
        if expected != actual:
            checksum_failures.append(f"{table}.{table_col}: raw sum {expected} != stored sum {actual}")

    result = Phase1Result(
        passed=not row_count_failures and not checksum_failures,
        reports=reports,
        row_count_failures=row_count_failures,
        checksum_failures=checksum_failures,
    )
    return store, result


def _print_report(store: FinancialStateStore, result: Phase1Result):
    print(f"{'file':<28}{'read':>7}{'normalized':>13}{'rejected':>10}")
    for r in result.reports:
        print(f"{r.source_file:<28}{r.rows_read:>7}{r.normalized:>13}{r.rejected:>10}")

    print()
    print("-- money checksums (raw CSV sum vs. stored sum, exact Decimal) --")
    for source_file, csv_col, table, table_col in _MONEY_CHECKS:
        expected = _raw_money_checksum(source_file, csv_col)
        actual = store.sum_decimal(table, table_col)
        status = "OK" if expected == actual else "MISMATCH"
        print(f"  {table}.{table_col:<14} raw={expected:<14} stored={actual:<14} [{status}]")

    print()
    if result.row_count_failures:
        print("ROW-COUNT INVARIANT FAILURES:")
        for f in result.row_count_failures:
            print(f"  - {f}")
    if result.checksum_failures:
        print("CHECKSUM FAILURES:")
        for f in result.checksum_failures:
            print(f"  - {f}")

    # provenance spot-check: prove one stored record traces back to its source row
    sample = store.all_rows("payments")[0]
    print()
    print(f"provenance spot-check: payments row 1 -> "
          f"source_file={sample['prov_source_file']!r}, "
          f"source_record_id={sample['prov_source_record_id']!r}, "
          f"row_number={sample['prov_row_number']}, "
          f"ingestion_run_id={sample['prov_ingestion_run_id']!r}")

    print()
    print("PHASE 1: PASS" if result.passed else "PHASE 1: FAIL")


if __name__ == "__main__":
    store, result = build_financial_state()
    _print_report(store, result)
    sys.exit(0 if result.passed else 1)
