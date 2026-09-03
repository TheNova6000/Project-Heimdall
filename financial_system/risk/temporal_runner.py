"""
Block 5's temporal-honesty benchmark for Risk -- companion to runner.py's
offline, full-history benchmark, not a replacement for it. Both are real,
both are kept: this file answers "if Risk only ever saw information
available at each customer's own decision time, what would precision/
recall have been," using the SAME real production code path
(compute_device_risk_signals(..., as_of=...)) proven in
a993b20's regression, not a reimplementation.

Per customer: the best (max) as-of score across every payment THEY
personally made -- i.e. "the most Risk could honestly have known about
this customer using only their own transaction history up to and
including their latest payment." This is the fairest honest comparison
against runner.py's own "best score across any device the customer
touches" methodology.

Run directly: `python -m financial_system.risk.temporal_runner`
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime

from financial_system.financial_graph.builder import build_graph
from financial_system.risk.risk_agent import run_risk_for_device
from financial_system.risk.runner import devices_with_sharers, load_labels
from financial_system.risk.scoring import risk_tier


def run(graph) -> dict[str, float]:
    device_ids = devices_with_sharers(graph)
    customer_best: dict[str, float] = defaultdict(float)

    for i, device_id in enumerate(device_ids, 1):
        # Every payment on this device is itself a decision point -- score
        # the device as-of EACH payment's own timestamp, and let that
        # payment's customer keep the max as-of score across their own
        # history (never another customer's later payment).
        payment_edges = graph.edges_to(device_id, "used_device")
        for e in payment_edges:
            payment = graph.get_node(e.subject_id)
            if not payment:
                continue
            cust_edges = graph.edges_to(e.subject_id, "initiated")
            if not cust_edges:
                continue
            cust_id = cust_edges[0].subject_id
            as_of = datetime.fromisoformat(payment.properties["created_at"])
            verdict = run_risk_for_device(graph, device_id, investigate=False, as_of=as_of)
            customer_best[cust_id] = max(customer_best[cust_id], verdict.decision_score)
        if i % 25 == 0 or i == len(device_ids):
            print(f"  [{i}/{len(device_ids)}] devices scored")

    return customer_best


def print_report(customer_best: dict[str, float], labels: list[dict]) -> bool:
    tp = fp = tn = fn = 0
    ring_tp = ring_fn = 0
    for row in labels:
        cid = row["customer_id"]
        is_fraud = row["is_fraud"] == "True"
        score = customer_best.get(cid, 0.0)
        predicted_fraud = risk_tier(score) == "HIGH"
        if predicted_fraud and is_fraud:
            tp += 1
        elif predicted_fraud and not is_fraud:
            fp += 1
        elif not predicted_fraud and is_fraud:
            fn += 1
        else:
            tn += 1
        if row["pattern"] == "fraud_ring":
            if predicted_fraud:
                ring_tp += 1
            else:
                ring_fn += 1

    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    print(f"\n-- Temporal (decision-time-honest) Risk benchmark ({len(labels)} customers) --")
    print(f"precision={precision:.1%}  recall={recall:.1%}  (tp={tp} fp={fp} tn={tn} fn={fn})")
    print(f"Fraud-ring recall: {ring_tp}/{ring_tp + ring_fn} ({ring_tp / max(ring_tp + ring_fn, 1):.1%})")
    print("\nThis is a DIFFERENT measurement from runner.py's offline benchmark, not a "
          "replacement for it: offline = full-history device-signature classification; "
          "temporal = honest decision-time-only classification. Both are real, both are kept.")
    return fp == 0  # the invariant that matters: honest scoping must never wrongly flag an innocent customer


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Building graph...")
    state, graph = build_graph()
    labels = load_labels()
    print("Scoring devices, as-of each observed payment...")
    customer_best = run(graph)
    passed = print_report(customer_best, labels)
    print("\nTEMPORAL RISK BENCHMARK: PASS (0 false positives)" if passed else
          "\nTEMPORAL RISK BENCHMARK: FAIL (a false positive appeared -- investigate)")
    sys.exit(0 if passed else 1)
