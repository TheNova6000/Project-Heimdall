"""
Verification check #1 -- Replay correctness (NORTH_STAR.md Section 24:
"Can the decision be replayed?" / Section 35: "replay correctness").

`financial_system/financial_state/builder.py` already proves an ingestion
invariant at BUILD time (row-count + money-checksum, per-source-file vs.
per-table). This module generalizes that same idea into a standalone
fingerprint that can be computed against ANY already-built
`FinancialStateStore` (not just immediately after ingestion), and adds the
piece builder.py's own self-check doesn't do: comparing two INDEPENDENT
builds of the same raw input against each other, byte-for-byte, to prove
the whole ingestion pipeline is a pure function of (raw_dir) -- not just
that one build didn't lose rows.

Deliberately excluded from the content hash: `prov_ingestion_run_id` and
`prov_ingested_at` (financial_state/store.py's `_PROV_COLUMNS`) -- both are
wall-clock/uuid values that are SUPPOSED to differ on every rebuild
(builder.py: `run_id = f"run_{uuid.uuid4().hex[:12]}"`), by design, not a
replay failure. Every other column, including the other three provenance
columns (source_file, source_record_id, row_number), is part of the
content hash -- a change there WOULD be a real replay failure (e.g. row
order silently changing which source row an id traces back to).

No entity_matches: `build_financial_state()` only touches Phase 1's raw
tables (see accounting_consistency_test.py's own comment on the same
gotcha -- a shared default db path must never be reused across an
unrelated build, since Phase 2's entity_matches lives in the same file but
isn't part of what Phase 1 rebuilds). This check therefore only fingerprints
the 11 raw-sourced tables Phase 1 itself owns.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from financial_system.financial_state.builder import build_financial_state
from financial_system.financial_state.store import FinancialStateStore

# Fixed order -- must match financial_state/builder.py's own _INGESTION_STEPS
# FK-dependency order, so the combined hash is deterministic across builds.
RAW_TABLES = [
    "merchants", "customers", "devices", "payment_instruments", "orders",
    "payments", "refunds", "fees", "settlements", "settlement_payments",
    "bank_transactions",
]

PK_COLUMNS = {
    "merchants": "merchant_id", "customers": "customer_id", "devices": "device_id",
    "payment_instruments": "instrument_id", "orders": "order_id", "payments": "payment_id",
    "refunds": "refund_id", "fees": "fee_id", "settlements": "settlement_id",
    "settlement_payments": "surrogate_id", "bank_transactions": "bank_txn_id",
}

# table -> money columns, generalized from builder.py's own _MONEY_CHECKS
# (which only covered 5 of these) to every money column in the schema.
MONEY_COLUMNS = {
    "orders": ["amount"],
    "payments": ["amount"],
    "refunds": ["amount"],
    "fees": ["fee_amount", "tax_amount"],
    "settlements": ["gross_amount", "fee_amount", "tax_amount", "net_amount"],
    "bank_transactions": ["amount"],
}

# Non-deterministic-by-design provenance columns -- excluded from the
# content hash only (row_counts/money_sums never touch these anyway).
_EXCLUDED_PROV_COLUMNS = {"prov_ingestion_run_id", "prov_ingested_at"}


@dataclass
class StoreFingerprint:
    row_counts: dict[str, int]
    money_sums: dict[str, str]      # "table.column" -> exact Decimal string
    content_hash: str               # sha256 hex, over every non-excluded column of every raw table
    # dataclass's generated __eq__ compares all three fields -- exactly the
    # "identical content" definition this check needs.


def compute_store_fingerprint(store: FinancialStateStore) -> StoreFingerprint:
    """Standalone -- works against any already-built FinancialStateStore,
    not just one this module built itself. This is the reusable primitive;
    verify_replay_correctness() below is one particular use of it (build
    twice, compare)."""
    row_counts = {t: store.count(t) for t in RAW_TABLES}

    money_sums = {}
    for table, cols in MONEY_COLUMNS.items():
        for col in cols:
            money_sums[f"{table}.{col}"] = str(store.sum_decimal(table, col))

    h = hashlib.sha256()
    for table in RAW_TABLES:
        pk = PK_COLUMNS[table]
        rows = [dict(r) for r in store.all_rows(table)]
        rows.sort(key=lambda d: d[pk])
        for d in rows:
            for excl in _EXCLUDED_PROV_COLUMNS:
                d.pop(excl, None)
            h.update(table.encode("utf-8"))
            h.update(b"\x00")
            h.update(json.dumps(d, sort_keys=True, default=str).encode("utf-8"))
            h.update(b"\x00")

    return StoreFingerprint(row_counts=row_counts, money_sums=money_sums, content_hash=h.hexdigest())


@dataclass
class ReplayResult:
    raw_dir: str
    n_replays: int
    identical: bool
    fingerprints: list[StoreFingerprint] = field(default_factory=list)
    row_count_diffs: dict[str, list[int]] = field(default_factory=dict)
    money_sum_diffs: dict[str, list[str]] = field(default_factory=dict)
    content_hash_diffs: list[str] = field(default_factory=list)


def _diff_fingerprints(fps: list[StoreFingerprint]) -> tuple[dict, dict, list]:
    row_count_diffs, money_sum_diffs, content_hash_diffs = {}, {}, []
    base = fps[0]
    for table, count in base.row_counts.items():
        values = [fp.row_counts[table] for fp in fps]
        if len(set(values)) > 1:
            row_count_diffs[table] = values
    for key, value in base.money_sums.items():
        values = [fp.money_sums[key] for fp in fps]
        if len(set(values)) > 1:
            money_sum_diffs[key] = values
    hashes = [fp.content_hash for fp in fps]
    if len(set(hashes)) > 1:
        content_hash_diffs = hashes
    return row_count_diffs, money_sum_diffs, content_hash_diffs


def verify_replay_correctness(raw_dir: Path, n_replays: int = 2,
                               work_dir: Path | None = None) -> ReplayResult:
    """Rebuilds the financial state store `n_replays` times from the SAME
    raw_dir, into independent, disposable db files (never
    financial_system/data/financial_state.db -- this must never collide
    with, or overwrite, the shared real-dataset db every runner reads),
    and fingerprints each build. `identical=True` iff every fingerprint
    (row counts, money sums, and the full-content hash) matches exactly."""
    own_tmp = work_dir is None
    work_dir = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="heimdall_verify_replay_"))
    work_dir.mkdir(parents=True, exist_ok=True)

    fingerprints: list[StoreFingerprint] = []
    for i in range(n_replays):
        db_path = work_dir / f"replay_{i}.db"
        store, _phase1_result = build_financial_state(db_path=db_path, raw_dir=raw_dir)
        fingerprints.append(compute_store_fingerprint(store))
        store.close()

    identical = all(fp == fingerprints[0] for fp in fingerprints[1:])
    row_count_diffs, money_sum_diffs, content_hash_diffs = (
        ({}, {}, []) if identical else _diff_fingerprints(fingerprints))

    return ReplayResult(
        raw_dir=str(raw_dir), n_replays=n_replays, identical=identical, fingerprints=fingerprints,
        row_count_diffs=row_count_diffs, money_sum_diffs=money_sum_diffs,
        content_hash_diffs=content_hash_diffs,
    )
