"""
Read-only graph queries: structural checks (orphans, fabrication, provenance
coverage) and the payment-journey reconstruction that's Phase 3's actual
milestone -- can we walk Customer -> Order -> Payment -> Settlement ->
BankTransaction (plus Fee/Refund) using nothing but graph edges?
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from financial_system.financial_graph.repository import GraphRepository
from financial_system.financial_state.store import FinancialStateStore


def edges_to_as_of(graph: GraphRepository, object_id: str, relation: str, as_of: datetime,
                    timestamp_field: str = "created_at") -> list:
    """The observation boundary a temporally-scoped agent needs, built once
    here rather than reimplemented per-agent. Block 5's hostile audit found
    Risk's device-sharing signal computed over a device's ENTIRE observed
    history regardless of decision time -- a real, measured leak (81/143
    payments on shared devices showed a full-history-vs-as-of tier
    mismatch, always in the over-flagging direction, since full history is
    a superset of what's known as-of any earlier point). This is the fix's
    shared primitive: GraphRepository itself stays a plain current-state
    store (no schema migration, no per-node-type temporal column), but any
    caller that needs a temporally honest observation set gets one edge
    query at a time, filtered by the SUBJECT node's own timestamp -- an
    edge whose subject doesn't exist yet at as_of carries no evidence at
    that decision time, structurally, not by agent-specific logic.
    Opt-in: omitting as_of at the call site (graph.edges_to() directly)
    preserves every existing caller's current behavior exactly."""
    edges = graph.edges_to(object_id, relation)
    result = []
    for e in edges:
        subject = graph.get_node(e.subject_id)
        if subject is None:
            continue
        ts = subject.properties.get(timestamp_field)
        if ts is not None and datetime.fromisoformat(ts) > as_of:
            continue
        result.append(e)
    return result

# Which property (or sum of properties) counts as "the amount" for a node type,
# for relevance ranking -- e.g. discovery_adapter's retriever prioritizing which
# facts to send an investigation when max_results truncates the neighborhood.
_AMOUNT_FIELDS = {
    "Payment": ("amount",), "Order": ("amount",), "BankTransaction": ("amount",),
    "Refund": ("amount",), "Settlement": ("net_amount",), "Fee": ("fee_amount", "tax_amount"),
}


def _node_amount(node) -> Decimal | None:
    fields = _AMOUNT_FIELDS.get(node.node_type)
    if not fields:
        return None
    total = Decimal("0")
    for f in fields:
        v = node.properties.get(f)
        if v is None:
            return None
        total += Decimal(str(v))
    return total


def check_no_orphaned_required_relationships(state: FinancialStateStore, graph: GraphRepository) -> list[str]:
    """Every Payment must have: an incoming `initiated` edge, and outgoing
    belongs_to/used_device/used_instrument edges. These are all FK-given, so
    100% coverage is the correct expectation -- any gap is a real Phase 3 bug."""
    failures = []
    n_payments = state.count("payments")
    for relation, direction in [("initiated", "to"), ("belongs_to", "from"),
                                 ("used_device", "from"), ("used_instrument", "from")]:
        actual = graph.count_edges(relation)
        if actual != n_payments:
            failures.append(f"{relation}: expected {n_payments} edges (1 per payment), got {actual}")
    return failures


def check_no_fabricated_relationships(graph: GraphRepository) -> list[str]:
    """Every edge's endpoints must be real nodes in this same graph."""
    failures = []
    for e in graph.all_edges():
        if not graph.node_exists(e.subject_id):
            failures.append(f"edge {e.relation} subject {e.subject_id!r} has no node")
        if not graph.node_exists(e.object_id):
            failures.append(f"edge {e.relation} object {e.object_id!r} has no node")
    return failures


def check_provenance_coverage(graph: GraphRepository) -> list[str]:
    """Every edge must carry non-empty evidence and source_record_ids."""
    failures = []
    for e in graph.all_edges():
        if not e.evidence or not e.source_record_ids:
            failures.append(f"edge {e.subject_id}-[{e.relation}]->{e.object_id} missing evidence/provenance")
    return failures


def _summarize(node) -> str:
    props = ", ".join(f"{k}={v}" for k, v in node.properties.items() if v is not None)
    return f"{node.node_type} {node.node_id}: {props}"


def reconciliation_neighborhood(graph: GraphRepository, subject_type: str, subject_id: str) -> list[dict]:
    """The 'small relevant evidence' an investigation actually needs (Phase 4) --
    never the whole graph. For a Settlement: the settlement itself, every payment
    it contains (duplicates preserved, not deduped -- a repeated payment IS
    evidence), each of those payments' fees/refunds, and any resolved bank
    transaction(s). For a Payment: its settlement(s) (and their bank
    transaction(s)), fees, and refunds.

    Each entry: {node_id, node_type, relation_from_subject, summary}. No LLM,
    no external call -- this is graph/deterministic intelligence (ARCHITECTURE.md
    §0, kind 1-2), what discovery_adapter's FinancialStateRetriever wraps into
    RetrievedResource objects for Discovery.AI to read.
    """
    facts: list[dict] = []
    seen_relations: set[tuple[str, str]] = set()

    def add(node_id: str, relation: str, allow_repeat: bool = False):
        node = graph.get_node(node_id)
        if not node:
            return
        key = (node_id, relation)
        if not allow_repeat and key in seen_relations:
            return
        seen_relations.add(key)
        facts.append({"node_id": node.node_id, "node_type": node.node_type,
                       "relation_from_subject": relation, "summary": _summarize(node),
                       "amount": _node_amount(node)})

    add(subject_id, "self")

    if subject_type == "Settlement":
        for e in graph.edges_from(subject_id, "contains"):
            # allow_repeat: a payment listed twice under `contains` (the
            # duplicate_record anomaly) must show up twice here too -- collapsing
            # it would hide the exact evidence that explains the exception.
            add(e.object_id, "contains", allow_repeat=True)
            for fe in graph.edges_from(e.object_id, "generates"):
                add(fe.object_id, f"generates (payment {e.object_id})")
            for re_ in graph.edges_from(e.object_id, "refunded_by"):
                add(re_.object_id, f"refunded_by (payment {e.object_id})")
        for be in graph.edges_from(subject_id, "deposited_as"):
            add(be.object_id, "deposited_as")

    elif subject_type == "Payment":
        for e in graph.edges_from(subject_id, "settles_into"):
            add(e.object_id, "settles_into")
            for be in graph.edges_from(e.object_id, "deposited_as"):
                add(be.object_id, f"deposited_as (settlement {e.object_id})")
        for fe in graph.edges_from(subject_id, "generates"):
            add(fe.object_id, "generates")
        for re_ in graph.edges_from(subject_id, "refunded_by"):
            add(re_.object_id, "refunded_by")

    return facts


def risk_neighborhood(graph: GraphRepository, device_id: str) -> list[dict]:
    """The evidence a risk investigation actually needs: the device itself,
    every customer sharing it, and every payment made on it (which customer,
    when, how much) -- the network Risk's deterministic signals were computed
    from, so Discovery.AI can explain the same numbers, never re-derive its
    own. Same shape as reconciliation_neighborhood() (node_id/node_type/
    relation_from_subject/summary/amount) so FinancialStateRetriever serves
    both without a second retriever class.
    """
    facts: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(node_id: str, relation: str):
        node = graph.get_node(node_id)
        if not node:
            return
        key = (node_id, relation)
        if key in seen:
            return
        seen.add(key)
        facts.append({"node_id": node.node_id, "node_type": node.node_type,
                       "relation_from_subject": relation, "summary": _summarize(node),
                       "amount": _node_amount(node)})

    add(device_id, "self")
    for e in graph.edges_to(device_id, "uses"):
        add(e.subject_id, "shares_device")
    for e in graph.edges_to(device_id, "used_device"):
        add(e.subject_id, "payment_on_device")

    return facts


def payment_journey(graph: GraphRepository, payment_id: str) -> dict:
    """Reconstructs one payment's full financial journey from graph edges only."""
    payment = graph.get_node(payment_id)
    if not payment:
        return {"payment_id": payment_id, "found": False}

    customer_edges = graph.edges_to(payment_id, "initiated")
    order_edges = graph.edges_from(payment_id, "belongs_to")
    device_edges = graph.edges_from(payment_id, "used_device")
    instrument_edges = graph.edges_from(payment_id, "used_instrument")
    settlement_edges = graph.edges_from(payment_id, "settles_into")
    refund_edges = graph.edges_from(payment_id, "refunded_by")
    fee_edges = graph.edges_from(payment_id, "generates")

    settlements = []
    for se in settlement_edges:
        bank_edges = graph.edges_from(se.object_id, "deposited_as")
        settlements.append({
            "settlement_id": se.object_id,
            "settlement_properties": graph.get_node(se.object_id).properties,
            "bank_transactions": [
                {"bank_txn_id": be.object_id, "properties": graph.get_node(be.object_id).properties}
                for be in bank_edges
            ],
        })

    return {
        "payment_id": payment_id,
        "found": True,
        "properties": payment.properties,
        "customer": customer_edges[0].subject_id if customer_edges else None,
        "order": order_edges[0].object_id if order_edges else None,
        "device": device_edges[0].object_id if device_edges else None,
        "instrument": instrument_edges[0].object_id if instrument_edges else None,
        "settlements": settlements,
        "refunds": [re.object_id for re in refund_edges],
        "fees": [fe.object_id for fe in fee_edges],
        "reaches_bank": any(s["bank_transactions"] for s in settlements),
    }


def format_journey(journey: dict) -> str:
    if not journey["found"]:
        return f"payment {journey['payment_id']}: NOT FOUND"
    lines = [
        f"Payment {journey['payment_id']}  amount={journey['properties']['amount']}  "
        f"status={journey['properties']['status']}",
        f"  Customer     -> {journey['customer']}",
        f"  Order        -> {journey['order']}",
        f"  Device       -> {journey['device']}",
        f"  Instrument   -> {journey['instrument']}",
    ]
    if journey["fees"]:
        lines.append(f"  Fees         -> {journey['fees']}")
    if journey["refunds"]:
        lines.append(f"  Refunds      -> {journey['refunds']}")
    if journey["settlements"]:
        for s in journey["settlements"]:
            btx = [b["bank_txn_id"] for b in s["bank_transactions"]] or ["(none -- unresolved)"]
            lines.append(f"  Settlement   -> {s['settlement_id']}  net={s['settlement_properties']['net_amount']}")
            lines.append(f"    BankTxn(s) -> {btx}")
    else:
        lines.append("  Settlement   -> (none -- payment failed or never settled)")
    lines.append(f"  reaches_bank = {journey['reaches_bank']}")
    return "\n".join(lines)
