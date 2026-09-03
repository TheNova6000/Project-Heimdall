"""
EventStore -- SQLite-backed, insert-only (no update method exists, same
discipline as financial_state's own insert-once tables). Enforces, at write
time, exactly the invariants MIGRATION_DESIGN.md specifies:
  - event_type must be in the closed taxonomy (§2)
  - dedup on (source, source_event_id) when source_event_id is set (§4)
  - causation_id, if set, must reference an event with occurred_at <= this
    event's occurred_at -- an event cannot be caused by a future event (§5)
  - recorded_at >= occurred_at -- an event cannot be learned about before it
    happened (§7, previously documented as expected but unenforced; see
    adversarial_test.py's former test_recorded_before_occurred_gap)
  - occurred_at/recorded_at are normalized to timezone-aware UTC before
    persistence, here and only here -- the write boundary is where this
    system decides what a timestamp means, not backfill/projection/any
    reader. A naive input is treated as already-UTC (the only assumption
    consistent with how this dataset's own naive CSV timestamps and this
    store's aware, datetime.now(timezone.utc)-sourced live events were
    already being compared before this fix, per the as_of report's finding).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from financial_system.events.models import Event
from financial_system.events.taxonomy import EVENT_TYPES


def _to_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    subject_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_event_id TEXT,
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    causation_id TEXT,
    supersedes_event_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_subject ON events(subject_id, event_type);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_source_dedup
    ON events(source, source_event_id) WHERE source_event_id IS NOT NULL;
"""


class InvalidEventType(Exception):
    pass


class DuplicateEvent(Exception):
    pass


class CausationOrderViolation(Exception):
    pass


class TemporalOrderViolation(Exception):
    pass


class EventStore:
    def __init__(self, db_path: str | Path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self):
        self._conn.close()

    def commit(self):
        self._conn.commit()

    def append(self, event: Event) -> None:
        if event.event_type not in EVENT_TYPES:
            raise InvalidEventType(f"{event.event_type!r} is not in the closed taxonomy")

        # Normalize here, once, at the write boundary -- not in the caller,
        # not in a reader. Everything downstream (append's own checks below,
        # every stored row from this point on, every comparison a reader
        # ever does) sees timezone-aware UTC only.
        occurred_at = _to_utc(event.occurred_at)
        recorded_at = _to_utc(event.recorded_at)

        if recorded_at < occurred_at:
            raise TemporalOrderViolation(
                f"{event.event_id}: recorded_at ({recorded_at.isoformat()}) is before "
                f"occurred_at ({occurred_at.isoformat()}) -- an event cannot be learned about "
                f"before it happened"
            )

        if event.causation_id:
            cause = self.get(event.causation_id)
            if cause and cause.occurred_at > occurred_at:
                raise CausationOrderViolation(
                    f"{event.event_id} (occurred_at={occurred_at}) cannot be caused by "
                    f"{event.causation_id} (occurred_at={cause.occurred_at}) -- an event cannot "
                    f"be caused by a future event"
                )

        try:
            self._conn.execute(
                "INSERT INTO events (event_id, event_type, schema_version, subject_id, source, "
                " source_event_id, occurred_at, recorded_at, payload, correlation_id, "
                " causation_id, supersedes_event_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event.event_id, event.event_type, event.schema_version, event.subject_id,
                 event.source, event.source_event_id, occurred_at.isoformat(),
                 recorded_at.isoformat(), json.dumps(event.payload), event.correlation_id,
                 event.causation_id, event.supersedes_event_id),
            )
        except sqlite3.IntegrityError as e:
            raise DuplicateEvent(
                f"event with source={event.source!r} source_event_id={event.source_event_id!r} "
                f"already recorded"
            ) from e

    def get(self, event_id: str) -> Event | None:
        row = self._conn.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        return self._row_to_event(row) if row else None

    def events_for_subject(self, subject_id: str, event_type: str | None = None) -> list[Event]:
        if event_type:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE subject_id = ? AND event_type = ? ORDER BY occurred_at",
                (subject_id, event_type)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM events WHERE subject_id = ? ORDER BY occurred_at",
                (subject_id,)).fetchall()
        return [self._row_to_event(r) for r in rows]

    def events_for_correlation(self, correlation_id: str) -> list[Event]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE correlation_id = ? ORDER BY occurred_at",
            (correlation_id,)).fetchall()
        return [self._row_to_event(r) for r in rows]

    def all_events(self, event_type: str | None = None, as_of: datetime | None = None) -> list[Event]:
        """as_of, when given, restricts the result to events with
        occurred_at <= as_of -- the one filter TEMPORAL_MODEL_SPEC.md's
        as_of projection semantics section requires. Omitting it (the
        default) is byte-identical to the pre-existing behavior."""
        clauses, params = [], []
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if as_of is not None:
            clauses.append("occurred_at <= ?")
            params.append(_to_utc(as_of).isoformat())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(f"SELECT * FROM events{where} ORDER BY occurred_at", params).fetchall()
        return [self._row_to_event(r) for r in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> Event:
        return Event(
            event_id=row["event_id"], event_type=row["event_type"],
            schema_version=row["schema_version"], subject_id=row["subject_id"],
            source=row["source"], source_event_id=row["source_event_id"],
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
            payload=json.loads(row["payload"]), correlation_id=row["correlation_id"],
            causation_id=row["causation_id"], supersedes_event_id=row["supersedes_event_id"],
        )
