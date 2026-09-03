"""
ActionStore -- SQLite-backed, keyed for idempotency lookup by
`idempotency_key`. This is the ONE store in the whole system with a real
UPDATE method (`update_execution_status`) -- Action.execution_status tracks
the command's own lifecycle (PENDING -> STARTED -> COMPLETED/FAILED/REJECTED),
which is a deliberate, explicitly-scoped exception to every other object's
insert-only discipline. It exists precisely so idempotency lookups have
something durable to check against; it never feeds the financial-state
projection (only ActionOutcomeObserved events do that).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from financial_system.action.models import Action

_SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    action_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    case_id TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    proposed_by TEXT NOT NULL,
    authorized_by TEXT NOT NULL,
    preconditions TEXT NOT NULL,
    expected_effect TEXT NOT NULL,
    created_at TEXT NOT NULL,
    execution_started_at TEXT,
    execution_completed_at TEXT,
    execution_status TEXT NOT NULL,
    result TEXT
);
"""


class ActionStore:
    def __init__(self, db_path: str | Path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self):
        self._conn.close()

    def commit(self):
        self._conn.commit()

    def create(self, action: Action) -> None:
        self._conn.execute(
            "INSERT INTO actions (action_id, idempotency_key, case_id, subject_id, action_type, "
            " proposed_by, authorized_by, preconditions, expected_effect, created_at, "
            " execution_started_at, execution_completed_at, execution_status, result) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (action.action_id, action.idempotency_key, action.case_id, action.subject_id,
             action.action_type, action.proposed_by, action.authorized_by,
             json.dumps(action.preconditions), action.expected_effect,
             action.created_at.isoformat(), None, None, action.execution_status, None),
        )

    def get_by_idempotency_key(self, idempotency_key: str) -> Action | None:
        row = self._conn.execute(
            "SELECT * FROM actions WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        return self._row_to_action(row) if row else None

    def get_by_action_id(self, action_id: str) -> Action | None:
        row = self._conn.execute(
            "SELECT * FROM actions WHERE action_id = ?", (action_id,)).fetchone()
        return self._row_to_action(row) if row else None

    def update_execution_status(self, action_id: str, status: str,
                                 started_at: datetime | None = None,
                                 completed_at: datetime | None = None,
                                 result: dict | None = None) -> None:
        """The one sanctioned UPDATE in this entire system -- see module docstring."""
        fields, values = ["execution_status = ?"], [status]
        if started_at is not None:
            fields.append("execution_started_at = ?")
            values.append(started_at.isoformat())
        if completed_at is not None:
            fields.append("execution_completed_at = ?")
            values.append(completed_at.isoformat())
        if result is not None:
            fields.append("result = ?")
            values.append(json.dumps(result))
        values.append(action_id)
        self._conn.execute(f"UPDATE actions SET {', '.join(fields)} WHERE action_id = ?", values)

    @staticmethod
    def _row_to_action(row: sqlite3.Row) -> Action:
        return Action(
            action_id=row["action_id"], idempotency_key=row["idempotency_key"],
            case_id=row["case_id"], subject_id=row["subject_id"], action_type=row["action_type"],
            proposed_by=row["proposed_by"], authorized_by=row["authorized_by"],
            preconditions=json.loads(row["preconditions"]), expected_effect=row["expected_effect"],
            created_at=datetime.fromisoformat(row["created_at"]),
            execution_started_at=datetime.fromisoformat(row["execution_started_at"])
                if row["execution_started_at"] else None,
            execution_completed_at=datetime.fromisoformat(row["execution_completed_at"])
                if row["execution_completed_at"] else None,
            execution_status=row["execution_status"],
            result=json.loads(row["result"]) if row["result"] else None,
        )
