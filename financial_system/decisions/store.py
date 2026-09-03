"""
DecisionStore -- SQLite-backed, insert-only (no update method, same
discipline as EventStore -- a recorded decision is a historical fact about
what was decided, never edited; DECISION_PROVENANCE_SPEC.md question 10:
a late event produces a NEW decision, it never edits an old one).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from financial_system.decisions.models import DecisionRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    agent TEXT NOT NULL,
    decision TEXT NOT NULL,
    decision_score REAL NOT NULL,
    reason TEXT NOT NULL,
    evidence TEXT NOT NULL,
    policy_outcome TEXT NOT NULL,
    policy_rule_id TEXT NOT NULL,
    world_as_of TEXT NOT NULL,
    logic_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    investigation_id TEXT,
    created_at TEXT NOT NULL,
    action_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_subject ON decisions(subject);
CREATE INDEX IF NOT EXISTS idx_decisions_action ON decisions(action_id);
"""


class DecisionStore:
    def __init__(self, db_path: str | Path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self):
        self._conn.close()

    def commit(self):
        self._conn.commit()

    def record(self, decision: DecisionRecord) -> None:
        self._conn.execute(
            "INSERT INTO decisions (decision_id, case_id, subject, agent, decision, "
            " decision_score, reason, evidence, policy_outcome, policy_rule_id, world_as_of, "
            " logic_version, policy_version, investigation_id, created_at, action_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (decision.decision_id, decision.case_id, decision.subject, decision.agent,
             decision.decision, decision.decision_score, decision.reason,
             json.dumps(decision.evidence), decision.policy_outcome, decision.policy_rule_id,
             decision.world_as_of.isoformat(), decision.logic_version, decision.policy_version,
             decision.investigation_id, decision.created_at.isoformat(), decision.action_id),
        )

    def get(self, decision_id: str) -> DecisionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)).fetchone()
        return self._row_to_decision(row) if row else None

    def get_by_action_id(self, action_id: str) -> DecisionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM decisions WHERE action_id = ?", (action_id,)).fetchone()
        return self._row_to_decision(row) if row else None

    def all_for_subject(self, subject: str) -> list[DecisionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM decisions WHERE subject = ? ORDER BY created_at", (subject,)).fetchall()
        return [self._row_to_decision(r) for r in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]

    @staticmethod
    def _row_to_decision(row: sqlite3.Row) -> DecisionRecord:
        return DecisionRecord(
            decision_id=row["decision_id"], case_id=row["case_id"], subject=row["subject"],
            agent=row["agent"], decision=row["decision"], decision_score=row["decision_score"],
            reason=row["reason"], evidence=json.loads(row["evidence"]),
            policy_outcome=row["policy_outcome"], policy_rule_id=row["policy_rule_id"],
            world_as_of=datetime.fromisoformat(row["world_as_of"]),
            logic_version=row["logic_version"], policy_version=row["policy_version"],
            investigation_id=row["investigation_id"],
            created_at=datetime.fromisoformat(row["created_at"]), action_id=row["action_id"],
        )
