"""
SQLite-backed Financial State store. This is the "normalized reality" layer
in ARCHITECTURE.md's three-layer memory -- source of truth for everything
above it (graph, agents), and itself sourced from data/raw/ (Phase 1 invariant).

Deliberately not an ORM: plain sqlite3 + explicit schema per Rules.md ("prefer
stdlib"). Money columns are TEXT (exact Decimal string), never REAL, so no
float ever touches a monetary comparison at this layer or above it.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from financial_system.financial_state.models import (
    BankTransaction, Customer, Device, Fee, Merchant, Order, Payment,
    PaymentInstrument, Provenance, Refund, Settlement, SettlementPayment,
)

_PROV_COLUMNS = (
    "prov_source_file TEXT NOT NULL",
    "prov_source_record_id TEXT NOT NULL",
    "prov_row_number INTEGER NOT NULL",
    "prov_ingestion_run_id TEXT NOT NULL",
    "prov_ingested_at TEXT NOT NULL",
)

# Tables that are NOT raw-sourced (no ingestion agent, no source-record provenance
# columns) -- currently just entity_matches, which carries its own evidence columns.
_NO_PROVENANCE_TABLES = {"entity_matches"}

_SCHEMA = {
    "merchants": (
        "merchant_id TEXT PRIMARY KEY", "name TEXT", "category TEXT", "created_at TEXT",
    ),
    "customers": (
        "customer_id TEXT PRIMARY KEY", "name TEXT", "email TEXT", "created_at TEXT",
    ),
    "devices": (
        "device_id TEXT PRIMARY KEY", "fingerprint TEXT", "first_seen_at TEXT",
    ),
    "payment_instruments": (
        "instrument_id TEXT PRIMARY KEY", "type TEXT", "masked_identifier TEXT", "customer_id TEXT",
    ),
    "orders": (
        "order_id TEXT PRIMARY KEY", "merchant_id TEXT", "customer_id TEXT",
        "amount TEXT", "currency TEXT", "created_at TEXT",
    ),
    "payments": (
        "payment_id TEXT PRIMARY KEY", "order_id TEXT", "customer_id TEXT", "merchant_id TEXT",
        "device_id TEXT", "instrument_id TEXT", "amount TEXT", "currency TEXT", "status TEXT",
        "failure_reason TEXT", "created_at TEXT", "authorized_at TEXT", "captured_at TEXT",
    ),
    "refunds": (
        "refund_id TEXT PRIMARY KEY", "payment_id TEXT", "amount TEXT", "reason TEXT", "created_at TEXT",
    ),
    "fees": (
        "fee_id TEXT PRIMARY KEY", "payment_id TEXT", "fee_amount TEXT", "tax_amount TEXT", "fee_type TEXT",
    ),
    "settlements": (
        "settlement_id TEXT PRIMARY KEY", "merchant_id TEXT", "settlement_date TEXT",
        "gross_amount TEXT", "fee_amount TEXT", "tax_amount TEXT", "net_amount TEXT",
    ),
    # No PK on (settlement_id, payment_id): a repeated pair is real source data
    # (e.g. the duplicate_record anomaly), not an ingestion error.
    "settlement_payments": (
        "surrogate_id INTEGER PRIMARY KEY AUTOINCREMENT", "settlement_id TEXT", "payment_id TEXT",
    ),
    "bank_transactions": (
        "bank_txn_id TEXT PRIMARY KEY", "utr TEXT", "amount TEXT", "value_date TEXT", "description TEXT",
    ),
    # Derived, not raw-sourced -- populated by entity_resolution/, not an ingestion agent.
    # No provenance columns: an EntityMatch's provenance IS source_record_ids + match_evidence.
    "entity_matches": (
        "match_id INTEGER PRIMARY KEY AUTOINCREMENT", "subject_type TEXT", "subject_id TEXT",
        "object_type TEXT", "object_id TEXT", "relation TEXT", "match_method TEXT",
        "match_score REAL", "match_evidence TEXT", "source_record_ids TEXT",
    ),
}


class DuplicateRecordError(Exception):
    """Raised when a source row's natural id collides with one already stored."""


def _prov_values(p: Provenance) -> tuple:
    return (p.source_file, p.source_record_id, p.row_number, p.ingestion_run_id, p.ingested_at.isoformat())


class FinancialStateStore:
    def __init__(self, db_path: str | Path = ":memory:"):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        for table, columns in _SCHEMA.items():
            if table in _NO_PROVENANCE_TABLES:
                cols = ", ".join(columns)
            else:
                cols = ", ".join(columns) + ", " + ", ".join(_PROV_COLUMNS)
            self._conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({cols})")
        self._conn.commit()

    def close(self):
        self._conn.close()

    # -- generic insert, shared by every typed add_* method below --
    def _insert(self, table: str, field_values: tuple, prov: Provenance):
        placeholders = ", ".join(["?"] * (len(field_values) + len(_PROV_COLUMNS)))
        try:
            self._conn.execute(
                f"INSERT INTO {table} VALUES ({placeholders})",
                field_values + _prov_values(prov),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateRecordError(str(e)) from e

    def commit(self):
        self._conn.commit()

    # -- typed add methods (explicit field order = table column order) --
    def add_merchant(self, m: Merchant):
        self._insert("merchants", (m.merchant_id, m.name, m.category, m.created_at.isoformat()), m.provenance)

    def add_customer(self, c: Customer):
        self._insert("customers", (c.customer_id, c.name, c.email, c.created_at.isoformat()), c.provenance)

    def add_device(self, d: Device):
        self._insert("devices", (d.device_id, d.fingerprint, d.first_seen_at.isoformat()), d.provenance)

    def add_instrument(self, i: PaymentInstrument):
        self._insert("payment_instruments",
                      (i.instrument_id, i.type, i.masked_identifier, i.customer_id), i.provenance)

    def add_order(self, o: Order):
        self._insert("orders", (o.order_id, o.merchant_id, o.customer_id, str(o.amount),
                                 o.currency, o.created_at.isoformat()), o.provenance)

    def add_payment(self, p: Payment):
        self._insert("payments", (
            p.payment_id, p.order_id, p.customer_id, p.merchant_id, p.device_id, p.instrument_id,
            str(p.amount), p.currency, p.status, p.failure_reason, p.created_at.isoformat(),
            p.authorized_at.isoformat() if p.authorized_at else None,
            p.captured_at.isoformat() if p.captured_at else None,
        ), p.provenance)

    def add_refund(self, r: Refund):
        self._insert("refunds", (r.refund_id, r.payment_id, str(r.amount), r.reason,
                                  r.created_at.isoformat()), r.provenance)

    def add_fee(self, f: Fee):
        self._insert("fees", (f.fee_id, f.payment_id, str(f.fee_amount), str(f.tax_amount),
                               f.fee_type), f.provenance)

    def add_settlement(self, s: Settlement):
        self._insert("settlements", (
            s.settlement_id, s.merchant_id, s.settlement_date.isoformat(),
            str(s.gross_amount), str(s.fee_amount), str(s.tax_amount), str(s.net_amount),
        ), s.provenance)

    def add_settlement_payment(self, sp: SettlementPayment):
        # surrogate_id is AUTOINCREMENT -- pass NULL to let sqlite assign it.
        placeholders = ", ".join(["?"] * (2 + len(_PROV_COLUMNS) + 1))
        self._conn.execute(
            f"INSERT INTO settlement_payments VALUES ({placeholders})",
            (None, sp.settlement_id, sp.payment_id) + _prov_values(sp.provenance),
        )

    def add_bank_transaction(self, b: BankTransaction):
        self._insert("bank_transactions", (b.bank_txn_id, b.utr, str(b.amount),
                                            b.value_date.isoformat(), b.description), b.provenance)

    def apply_payment_retry_success(self, payment_id: str, observed_at) -> None:
        """Stage 4's ONE sanctioned Payment mutation (MIGRATION_DESIGN.md's
        events/action_projection.py is the only caller). Mirrors Action.
        execution_status's own narrow, explicit exception to this project's
        insert-only discipline -- driven exclusively by a projected
        ActionOutcomeObserved(SUCCESS) event, never called directly by any
        agent, never by anything but the projector."""
        self._conn.execute(
            "UPDATE payments SET status = 'success', failure_reason = NULL, captured_at = ? "
            "WHERE payment_id = ?",
            (observed_at.isoformat() if hasattr(observed_at, "isoformat") else observed_at, payment_id),
        )

    def clear_entity_matches(self):
        self._conn.execute("DELETE FROM entity_matches")

    def add_entity_match(self, subject_type: str, subject_id: str, object_type: str, object_id: str,
                          relation: str, match_method: str, match_score: float,
                          match_evidence: list[str], source_record_ids: list[str]):
        self._conn.execute(
            "INSERT INTO entity_matches "
            "(subject_type, subject_id, object_type, object_id, relation, match_method, "
            " match_score, match_evidence, source_record_ids) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (subject_type, subject_id, object_type, object_id, relation, match_method,
             match_score, "; ".join(match_evidence), "; ".join(source_record_ids)),
        )

    # -- reads --
    def exists(self, table: str, id_column: str, id_value: str) -> bool:
        row = self._conn.execute(f"SELECT 1 FROM {table} WHERE {id_column} = ?", (id_value,)).fetchone()
        return row is not None

    def count(self, table: str) -> int:
        return self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def all_rows(self, table: str) -> Iterable[sqlite3.Row]:
        return self._conn.execute(f"SELECT * FROM {table}").fetchall()

    def sum_decimal(self, table: str, column: str) -> Decimal:
        """Exact-precision sum, computed in Python over Decimal -- sqlite's own
        SUM() would coerce the TEXT column through floating point."""
        total = Decimal("0")
        for row in self._conn.execute(f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"):
            total += Decimal(row[0])
        return total
