"""
Reference-data ingestion: merchants, customers, devices, payment instruments,
orders. Not one of the five transaction-event agents named in Phases.md, but
a prerequisite for them -- payment_ingestion.py can't validate a payment's
customer_id/merchant_id/device_id/instrument_id foreign keys without these
tables already loaded. Runs first in builder.py's ingestion order.
"""
from __future__ import annotations

from pathlib import Path

from financial_system.financial_state.models import (
    Customer, Device, Merchant, Order, PaymentInstrument,
)
from financial_system.financial_state.store import DuplicateRecordError, FinancialStateStore
from financial_system.ingestion.base import (
    IngestionReport, make_provenance, parse_decimal, parse_optional_dt, read_csv_rows,
)


def ingest_merchants(store: FinancialStateStore, raw_dir: Path, run_id: str) -> IngestionReport:
    source_file = "merchants.csv"
    report = IngestionReport(source_file)
    for row_number, row in read_csv_rows(raw_dir / source_file):
        report.rows_read += 1
        rid = row.get("merchant_id", "")
        try:
            if not rid or not row.get("name") or not row.get("created_at"):
                raise ValueError("missing required field")
            m = Merchant(
                merchant_id=rid, name=row["name"], category=row.get("category", ""),
                created_at=parse_optional_dt(row["created_at"]),
                provenance=make_provenance(source_file, rid, row_number, run_id),
            )
            store.add_merchant(m)
            report.normalized += 1
        except (ValueError, DuplicateRecordError) as e:
            report.add_reject(row_number, rid, str(e))
    return report


def ingest_customers(store: FinancialStateStore, raw_dir: Path, run_id: str) -> IngestionReport:
    source_file = "customers.csv"
    report = IngestionReport(source_file)
    for row_number, row in read_csv_rows(raw_dir / source_file):
        report.rows_read += 1
        rid = row.get("customer_id", "")
        try:
            if not rid or not row.get("created_at"):
                raise ValueError("missing required field")
            c = Customer(
                customer_id=rid, name=row.get("name", ""), email=row.get("email", ""),
                created_at=parse_optional_dt(row["created_at"]),
                provenance=make_provenance(source_file, rid, row_number, run_id),
            )
            store.add_customer(c)
            report.normalized += 1
        except (ValueError, DuplicateRecordError) as e:
            report.add_reject(row_number, rid, str(e))
    return report


def ingest_devices(store: FinancialStateStore, raw_dir: Path, run_id: str) -> IngestionReport:
    source_file = "devices.csv"
    report = IngestionReport(source_file)
    for row_number, row in read_csv_rows(raw_dir / source_file):
        report.rows_read += 1
        rid = row.get("device_id", "")
        try:
            if not rid or not row.get("first_seen_at"):
                raise ValueError("missing required field")
            d = Device(
                device_id=rid, fingerprint=row.get("fingerprint", ""),
                first_seen_at=parse_optional_dt(row["first_seen_at"]),
                provenance=make_provenance(source_file, rid, row_number, run_id),
            )
            store.add_device(d)
            report.normalized += 1
        except (ValueError, DuplicateRecordError) as e:
            report.add_reject(row_number, rid, str(e))
    return report


def ingest_instruments(store: FinancialStateStore, raw_dir: Path, run_id: str) -> IngestionReport:
    source_file = "payment_instruments.csv"
    report = IngestionReport(source_file)
    for row_number, row in read_csv_rows(raw_dir / source_file):
        report.rows_read += 1
        rid = row.get("instrument_id", "")
        try:
            if not rid or not row.get("customer_id"):
                raise ValueError("missing required field")
            if not store.exists("customers", "customer_id", row["customer_id"]):
                raise ValueError(f"unknown customer_id {row['customer_id']!r}")
            i = PaymentInstrument(
                instrument_id=rid, type=row.get("type", ""),
                masked_identifier=row.get("masked_identifier", ""), customer_id=row["customer_id"],
                provenance=make_provenance(source_file, rid, row_number, run_id),
            )
            store.add_instrument(i)
            report.normalized += 1
        except (ValueError, DuplicateRecordError) as e:
            report.add_reject(row_number, rid, str(e))
    return report


def ingest_orders(store: FinancialStateStore, raw_dir: Path, run_id: str) -> IngestionReport:
    source_file = "orders.csv"
    report = IngestionReport(source_file)
    for row_number, row in read_csv_rows(raw_dir / source_file):
        report.rows_read += 1
        rid = row.get("order_id", "")
        try:
            if not rid or not row.get("amount") or not row.get("created_at"):
                raise ValueError("missing required field")
            if not store.exists("merchants", "merchant_id", row["merchant_id"]):
                raise ValueError(f"unknown merchant_id {row['merchant_id']!r}")
            if not store.exists("customers", "customer_id", row["customer_id"]):
                raise ValueError(f"unknown customer_id {row['customer_id']!r}")
            o = Order(
                order_id=rid, merchant_id=row["merchant_id"], customer_id=row["customer_id"],
                amount=parse_decimal(row["amount"]), currency=row.get("currency", "INR"),
                created_at=parse_optional_dt(row["created_at"]),
                provenance=make_provenance(source_file, rid, row_number, run_id),
            )
            store.add_order(o)
            report.normalized += 1
        except (ValueError, DuplicateRecordError) as e:
            report.add_reject(row_number, rid, str(e))
    return report
