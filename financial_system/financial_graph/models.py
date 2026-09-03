"""
Graph node/edge shapes. Deliberately identical in spirit to Discovery.AI's own
Node/relation model (ARCHITECTURE.md §1) so financial_graph/repository.py can
be swapped for a real Neo4j-backed implementation later without touching
builder.py or queries.py -- see repository.py's module docstring for why
SQLite stands in for Neo4j right now.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class GraphNode(BaseModel):
    node_id: str
    node_type: str              # "Payment", "Customer", "Settlement", ...
    properties: dict[str, Any]
    source_record_ids: list[str]


class GraphEdge(BaseModel):
    subject_id: str
    subject_type: str
    relation: str                # from ARCHITECTURE.md §1.2's FINANCIAL relation family
    object_id: str
    object_type: str
    match_method: str            # "foreign_key" | "deterministic_description" | "probabilistic" |
                                  # "probabilistic_disambiguated" | "derived_aggregation"
    match_score: float
    evidence: list[str]
    source_record_ids: list[str]
