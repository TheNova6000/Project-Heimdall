"""Shared plumbing for the ingestion agents: CSV row reading, provenance
construction, and the reject/report shapes every agent returns. No entity-
specific logic lives here -- each ingestion_*.py owns its own validation."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

from financial_system.financial_state.models import Provenance


@dataclass
class Reject:
    source_file: str
    row_number: int
    source_record_id: str
    reason: str


@dataclass
class IngestionReport:
    source_file: str
    rows_read: int = 0
    normalized: int = 0
    rejected: int = 0
    rejects: list[Reject] = field(default_factory=list)

    def add_reject(self, row_number: int, source_record_id: str, reason: str):
        self.rejects.append(Reject(self.source_file, row_number, source_record_id, reason))
        self.rejected += 1


def read_csv_rows(path: Path) -> Iterator[tuple[int, dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=1):
            yield row_number, row


def make_provenance(source_file: str, source_record_id: str, row_number: int,
                     ingestion_run_id: str) -> Provenance:
    return Provenance(
        source_file=source_file,
        source_record_id=source_record_id,
        row_number=row_number,
        ingestion_run_id=ingestion_run_id,
        ingested_at=datetime.now(timezone.utc),
    )


def parse_optional_dt(value: str) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as e:
        raise ValueError(f"not a valid decimal: {value!r}") from e
