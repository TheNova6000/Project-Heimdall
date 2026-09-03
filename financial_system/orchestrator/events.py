"""
Event classification + routing table. No live event bus exists in this
system, so `classify_event_types` reconstructs, deterministically from the
graph, what event types WOULD have fired for a given payment -- functionally
equivalent to a real event-driven router without pretending we have one.

Not every payment triggers every agent (ARCHITECTURE.md's own point: keeping
compute/complexity under control). PAYMENT_CREATED always fires (every
payment is a candidate for Risk's device-sharing check); PAYMENT_FAILED only
for a failed payment (Recovery); SETTLEMENT_RECEIVED only once a payment is
actually linked to a settlement (Controller).
"""
from __future__ import annotations

from financial_system.financial_graph.repository import GraphRepository

EVENT_AGENT_MAP = {
    "PAYMENT_CREATED": ["risk"],
    "PAYMENT_FAILED": ["recovery"],
    "SETTLEMENT_RECEIVED": ["controller"],
}


def classify_event_types(graph: GraphRepository, payment_id: str) -> list[str]:
    payment = graph.get_node(payment_id)
    if not payment:
        return []

    events = ["PAYMENT_CREATED"]
    if payment.properties.get("status") == "failed":
        events.append("PAYMENT_FAILED")
    if graph.edges_from(payment_id, "settles_into"):
        events.append("SETTLEMENT_RECEIVED")
    return events


def agents_for_events(events: list[str]) -> list[str]:
    return sorted({agent for e in events for agent in EVENT_AGENT_MAP.get(e, [])})
