"""
Phase 3: builds the Financial Event Graph from Financial State (Phase 1) +
resolved matches (Phase 2). Invents nothing -- every node and edge traces to
a source record via source_record_ids, exactly the chain ARCHITECTURE.md's
raw -> normalized -> graph layering requires.

Two edge sources, both legitimate, kept visibly distinct in this file:
  (a) Phase 2's persisted entity_matches -- belongs_to, initiated, used_device,
      used_instrument, settles_into/contains, deposited_as.
  (b) Derived here, because Phase 2's build order never covered them:
      generates (Payment->Fee), refunded_by (Payment->Refund), deducts
      (Settlement->Fee, bridged through settles_into), uses (Customer->Device,
      aggregated -- no direct FK exists for this) and uses (Customer->
      PaymentInstrument, a direct FK on payment_instruments, NOT aggregated --
      more complete, since it covers instruments never actually used in a
      payment too).

settles_into (temporal, Payment's lifecycle) and contains (composition,
Settlement's structure) are kept as two distinct typed edges over the same
node pair deliberately -- see relation_types.py's family split in
ARCHITECTURE.md §1.2. Not a duplicate.

Run directly: `python -m financial_system.financial_graph.builder`
"""
from __future__ import annotations

import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from financial_system.financial_graph.models import GraphEdge, GraphNode
from financial_system.financial_graph.repository import GraphRepository
from financial_system.financial_state.store import FinancialStateStore

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DB = REPO_ROOT / "financial_system" / "data" / "financial_state.db"
GRAPH_DB = REPO_ROOT / "financial_system" / "data" / "financial_graph.db"


def _node(node_id, node_type, properties, source_record_ids=None) -> GraphNode:
    return GraphNode(node_id=node_id, node_type=node_type, properties=properties,
                      source_record_ids=source_record_ids or [node_id])


def _build_nodes(state: FinancialStateStore, graph: GraphRepository):
    for r in state.all_rows("merchants"):
        graph.add_node(_node(r["merchant_id"], "Merchant", {"name": r["name"], "category": r["category"]}))
    for r in state.all_rows("customers"):
        graph.add_node(_node(r["customer_id"], "Customer", {"name": r["name"], "created_at": r["created_at"]}))
    for r in state.all_rows("devices"):
        graph.add_node(_node(r["device_id"], "Device",
                              {"fingerprint": r["fingerprint"], "first_seen_at": r["first_seen_at"]}))
    for r in state.all_rows("payment_instruments"):
        graph.add_node(_node(r["instrument_id"], "PaymentInstrument",
                              {"type": r["type"], "masked_identifier": r["masked_identifier"]}))
    for r in state.all_rows("orders"):
        graph.add_node(_node(r["order_id"], "Order", {"amount": r["amount"], "currency": r["currency"]}))
    for r in state.all_rows("payments"):
        graph.add_node(_node(r["payment_id"], "Payment",
                              {"amount": r["amount"], "status": r["status"],
                               "failure_reason": r["failure_reason"],
                               "created_at": r["created_at"], "captured_at": r["captured_at"]}))
    for r in state.all_rows("settlements"):
        graph.add_node(_node(r["settlement_id"], "Settlement",
                              {"net_amount": r["net_amount"], "settlement_date": r["settlement_date"]}))
    for r in state.all_rows("bank_transactions"):
        graph.add_node(_node(r["bank_txn_id"], "BankTransaction",
                              {"amount": r["amount"], "value_date": r["value_date"]}))
    for r in state.all_rows("refunds"):
        graph.add_node(_node(r["refund_id"], "Refund", {"amount": r["amount"], "reason": r["reason"]}))
    for r in state.all_rows("fees"):
        graph.add_node(_node(r["fee_id"], "Fee", {"fee_amount": r["fee_amount"], "tax_amount": r["tax_amount"]}))


def _edge_from_match(row) -> list[GraphEdge]:
    """Maps one persisted Phase 2 EntityMatch row onto 1-2 graph edges."""
    evidence = row["match_evidence"].split("; ")
    sources = row["source_record_ids"].split("; ")
    method, score = row["match_method"], row["match_score"]
    st, sid, ot, oid, relation = (row["subject_type"], row["subject_id"],
                                   row["object_type"], row["object_id"], row["relation"])

    if relation == "initiated_by":  # Payment->Customer given; canonical direction is Customer-initiated->Payment
        return [GraphEdge(subject_id=oid, subject_type=ot, relation="initiated",
                           object_id=sid, object_type=st, match_method=method, match_score=score,
                           evidence=evidence, source_record_ids=sources)]
    if relation == "deposited_as":  # BankTransaction->Settlement given; canonical direction is Settlement-deposited_as->BankTransaction
        return [GraphEdge(subject_id=oid, subject_type=ot, relation="deposited_as",
                           object_id=sid, object_type=st, match_method=method, match_score=score,
                           evidence=evidence, source_record_ids=sources)]
    if relation == "settles_into":  # keep as-is, AND add the composition inverse
        forward = GraphEdge(subject_id=sid, subject_type=st, relation="settles_into",
                             object_id=oid, object_type=ot, match_method=method, match_score=score,
                             evidence=evidence, source_record_ids=sources)
        inverse = GraphEdge(subject_id=oid, subject_type=ot, relation="contains",
                             object_id=sid, object_type=st, match_method=method, match_score=score,
                             evidence=evidence, source_record_ids=sources)
        return [forward, inverse]
    # belongs_to, used_device, used_instrument: kept exactly as resolved
    return [GraphEdge(subject_id=sid, subject_type=st, relation=relation, object_id=oid, object_type=ot,
                       match_method=method, match_score=score, evidence=evidence, source_record_ids=sources)]


def _build_edges_from_matches(state: FinancialStateStore, graph: GraphRepository):
    for row in state.all_rows("entity_matches"):
        for edge in _edge_from_match(row):
            graph.add_edge(edge)


def _build_derived_edges(state: FinancialStateStore, graph: GraphRepository):
    # Payment -[generates]-> Fee (direct FK, not covered by Phase 2)
    for r in state.all_rows("fees"):
        graph.add_edge(GraphEdge(
            subject_id=r["payment_id"], subject_type="Payment", relation="generates",
            object_id=r["fee_id"], object_type="Fee", match_method="foreign_key", match_score=1.0,
            evidence=["fees.payment_id given directly by source"],
            source_record_ids=[r["payment_id"], r["fee_id"]],
        ))

    # Payment -[refunded_by]-> Refund (direct FK, not covered by Phase 2)
    for r in state.all_rows("refunds"):
        graph.add_edge(GraphEdge(
            subject_id=r["payment_id"], subject_type="Payment", relation="refunded_by",
            object_id=r["refund_id"], object_type="Refund", match_method="foreign_key", match_score=1.0,
            evidence=["refunds.payment_id given directly by source"],
            source_record_ids=[r["payment_id"], r["refund_id"]],
        ))

    # Customer -[uses]-> PaymentInstrument (direct FK -- more complete than aggregating
    # over payments, since it covers instruments never actually used yet)
    for r in state.all_rows("payment_instruments"):
        graph.add_edge(GraphEdge(
            subject_id=r["customer_id"], subject_type="Customer", relation="uses",
            object_id=r["instrument_id"], object_type="PaymentInstrument",
            match_method="foreign_key", match_score=1.0,
            evidence=["payment_instruments.customer_id given directly by source"],
            source_record_ids=[r["customer_id"], r["instrument_id"]],
        ))

    # Customer -[uses]-> Device -- NO direct FK exists (devices.csv has no owning
    # customer); aggregated over payment history instead, deduped, evidence lists
    # every payment that exhibits the pairing.
    pairs: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in state.all_rows("payments"):
        pairs[(r["customer_id"], r["device_id"])].append(r["payment_id"])
    for (customer_id, device_id), payment_ids in pairs.items():
        graph.add_edge(GraphEdge(
            subject_id=customer_id, subject_type="Customer", relation="uses",
            object_id=device_id, object_type="Device", match_method="derived_aggregation",
            match_score=1.0, evidence=[f"observed in {len(payment_ids)} payment(s)"],
            source_record_ids=[customer_id, device_id] + payment_ids,
        ))

    # Settlement -[deducts]-> Fee -- bridged through settles_into, deduped per
    # (settlement, fee) pair (the duplicate_record anomaly's duplication belongs
    # on settles_into/contains, not amplified into this derived edge).
    payment_to_settlements: dict[str, set[str]] = defaultdict(set)
    for e in graph.all_edges():
        if e.relation == "settles_into":
            payment_to_settlements[e.subject_id].add(e.object_id)
    for r in state.all_rows("fees"):
        for settlement_id in payment_to_settlements.get(r["payment_id"], ()):
            graph.add_edge(GraphEdge(
                subject_id=settlement_id, subject_type="Settlement", relation="deducts",
                object_id=r["fee_id"], object_type="Fee", match_method="derived_aggregation",
                match_score=1.0,
                evidence=[f"bridged via payment {r['payment_id']} (settles_into)"],
                source_record_ids=[settlement_id, r["payment_id"], r["fee_id"]],
            ))


def build_graph(state_db: Path = STATE_DB, graph_db: Path = GRAPH_DB) -> tuple[FinancialStateStore, GraphRepository]:
    if not state_db.exists():
        raise SystemExit("financial_state.db not found -- run Phase 1 first.")
    state = FinancialStateStore(state_db)
    if graph_db.exists():
        graph_db.unlink()  # fresh graph every run, same reproducibility rule as Phase 1
    graph = GraphRepository(graph_db)

    _build_nodes(state, graph)
    graph.commit()
    _build_edges_from_matches(state, graph)
    graph.commit()
    _build_derived_edges(state, graph)
    graph.commit()
    return state, graph


def _print_report(state: FinancialStateStore, graph: GraphRepository):
    import json

    from financial_system.financial_graph.queries import (
        check_no_fabricated_relationships, check_no_orphaned_required_relationships,
        check_provenance_coverage, format_journey, payment_journey,
    )

    print("-- node counts --")
    for node_type, n in sorted(graph.node_type_counts().items()):
        print(f"  {node_type:<18} {n}")

    print()
    print("-- edge counts by relation --")
    for relation, n in sorted(graph.relation_counts().items()):
        print(f"  {relation:<18} {n}")

    print()
    orphan_failures = check_no_orphaned_required_relationships(state, graph)
    fabrication_failures = check_no_fabricated_relationships(graph)
    provenance_failures = check_provenance_coverage(graph)
    print(f"orphaned required relationships: {len(orphan_failures)}"
          + ("" if not orphan_failures else f" -- {orphan_failures}"))
    print(f"fabricated relationships:        {len(fabrication_failures)}"
          + ("" if not fabrication_failures else f" -- {fabrication_failures[:3]}"))
    print(f"provenance coverage gaps:        {len(provenance_failures)}"
          + ("" if not provenance_failures else f" -- {provenance_failures[:3]}"))

    n_fees_without_settlement = sum(
        1 for r in state.all_rows("fees") if not graph.edges_to(r["fee_id"], "deducts")
    )
    print(f"fees with no settlement (expected -- missing_settlement anomaly): {n_fees_without_settlement}")

    print()
    print("-- payment journey reconstruction (the Phase 3 milestone) --")
    manifest_path = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "case_manifest.json"
    sample_ids = []
    if manifest_path.exists():
        for case in json.loads(manifest_path.read_text(encoding="utf-8")):
            if "payment_id" in case and case["payment_id"] not in sample_ids:
                sample_ids.append(case["payment_id"])
    for pid in sample_ids[:4]:
        print(format_journey(payment_journey(graph, pid)))
        print()

    passed = not orphan_failures and not fabrication_failures and not provenance_failures
    print("PHASE 3: PASS" if passed else "PHASE 3: FAIL")
    return passed


if __name__ == "__main__":
    state, graph = build_graph()
    passed = _print_report(state, graph)
    sys.exit(0 if passed else 1)
