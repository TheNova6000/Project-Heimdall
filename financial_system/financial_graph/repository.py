"""
GraphRepository: a Neo4j-shaped store, backed by SQLite.

Why not Neo4j right now: this environment has no Docker and no `neo4j` driver
installed, so there's no Neo4j instance to write to yet (Discovery.AI's own
setup needs `docker compose up -d`). Rather than block Phase 3 on standing up
infra, or silently pretend SQLite IS the graph layer, this repository exposes
exactly the interface a Neo4j-backed one would (typed nodes, typed directed
edges, evidence, provenance, neighbor/relation queries) so that swapping the
implementation later -- when discovery_adapter needs Risk/Controller/Recovery
to share the same graph Discovery.AI's investigator reads -- means writing a
Neo4jGraphRepository against this same interface, not restructuring
builder.py or queries.py.

Node upsert is idempotent (unlike financial_state's ingestion, which rejects
a duplicate id) -- many edges legitimately reference the same node (e.g. one
Customer node is the object of hundreds of Payment edges), so "add this node
if it doesn't already exist" is the correct operation here, not "insert
exactly once."
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from financial_system.financial_graph.models import GraphEdge, GraphNode

_SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL,
    properties TEXT NOT NULL,
    source_record_ids TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    relation TEXT NOT NULL,
    object_id TEXT NOT NULL,
    object_type TEXT NOT NULL,
    match_method TEXT NOT NULL,
    match_score REAL NOT NULL,
    evidence TEXT NOT NULL,
    source_record_ids TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_edges_subject ON graph_edges(subject_id, relation);
CREATE INDEX IF NOT EXISTS idx_edges_object ON graph_edges(object_id, relation);
"""


class GraphRepository:
    def __init__(self, db_path: str | Path):
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)

    def close(self):
        self._conn.close()

    def commit(self):
        self._conn.commit()

    def reset(self):
        self._conn.executescript("DELETE FROM graph_nodes; DELETE FROM graph_edges;")

    # -- writes --
    def add_node(self, node: GraphNode):
        self._conn.execute(
            "INSERT OR IGNORE INTO graph_nodes (node_id, node_type, properties, source_record_ids) "
            "VALUES (?, ?, ?, ?)",
            (node.node_id, node.node_type, json.dumps(node.properties),
             json.dumps(node.source_record_ids)),
        )

    def add_edge(self, edge: GraphEdge):
        self._conn.execute(
            "INSERT INTO graph_edges (subject_id, subject_type, relation, object_id, object_type, "
            " match_method, match_score, evidence, source_record_ids) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (edge.subject_id, edge.subject_type, edge.relation, edge.object_id, edge.object_type,
             edge.match_method, edge.match_score, json.dumps(edge.evidence),
             json.dumps(edge.source_record_ids)),
        )

    # -- reads --
    def get_node(self, node_id: str) -> GraphNode | None:
        row = self._conn.execute("SELECT * FROM graph_nodes WHERE node_id = ?", (node_id,)).fetchone()
        return self._row_to_node(row) if row else None

    def node_exists(self, node_id: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM graph_nodes WHERE node_id = ?", (node_id,)).fetchone() is not None

    def edges_from(self, subject_id: str, relation: str | None = None) -> list[GraphEdge]:
        if relation:
            rows = self._conn.execute(
                "SELECT * FROM graph_edges WHERE subject_id = ? AND relation = ?",
                (subject_id, relation)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM graph_edges WHERE subject_id = ?", (subject_id,)).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def edges_to(self, object_id: str, relation: str | None = None) -> list[GraphEdge]:
        if relation:
            rows = self._conn.execute(
                "SELECT * FROM graph_edges WHERE object_id = ? AND relation = ?",
                (object_id, relation)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM graph_edges WHERE object_id = ?", (object_id,)).fetchall()
        return [self._row_to_edge(r) for r in rows]

    def count_nodes(self, node_type: str | None = None) -> int:
        if node_type:
            return self._conn.execute(
                "SELECT COUNT(*) FROM graph_nodes WHERE node_type = ?", (node_type,)).fetchone()[0]
        return self._conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]

    def count_edges(self, relation: str | None = None) -> int:
        if relation:
            return self._conn.execute(
                "SELECT COUNT(*) FROM graph_edges WHERE relation = ?", (relation,)).fetchone()[0]
        return self._conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]

    def relation_counts(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT relation, COUNT(*) as n FROM graph_edges GROUP BY relation").fetchall()
        return {r["relation"]: r["n"] for r in rows}

    def node_type_counts(self) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT node_type, COUNT(*) as n FROM graph_nodes GROUP BY node_type").fetchall()
        return {r["node_type"]: r["n"] for r in rows}

    def all_edges(self) -> list[GraphEdge]:
        return [self._row_to_edge(r) for r in self._conn.execute("SELECT * FROM graph_edges").fetchall()]

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> GraphNode:
        return GraphNode(node_id=row["node_id"], node_type=row["node_type"],
                          properties=json.loads(row["properties"]),
                          source_record_ids=json.loads(row["source_record_ids"]))

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> GraphEdge:
        return GraphEdge(subject_id=row["subject_id"], subject_type=row["subject_type"],
                          relation=row["relation"], object_id=row["object_id"],
                          object_type=row["object_type"], match_method=row["match_method"],
                          match_score=row["match_score"], evidence=json.loads(row["evidence"]),
                          source_record_ids=json.loads(row["source_record_ids"]))
