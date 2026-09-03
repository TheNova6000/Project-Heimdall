"""
Phase 6 done check (Phases.md): precision/recall/false-positive rate against
risk_labels.csv, reported separately for fraud_ring vs benign_shared_device --
the second number is what proves the agent isn't just flagging every shared
device. 4A-only (investigate=False) by default, same discipline as Controller:
Risk's whole point is not needing an LLM call to produce a score.

Run directly: `python -m financial_system.risk.runner`
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

from financial_system.financial_graph.builder import build_graph
from financial_system.risk.risk_agent import run_risk_for_device
from financial_system.risk.scoring import risk_tier

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "risk_labels.csv"


def load_labels() -> list[dict]:
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def devices_with_sharers(graph) -> list[str]:
    """Every device with >=2 distinct customers sharing it via a `uses` edge --
    the only devices signals.py can produce a nonzero risk score for."""
    device_customers: dict[str, set] = defaultdict(set)
    for e in graph.all_edges():
        if e.relation == "uses" and e.object_type == "Device":
            device_customers[e.object_id].add(e.subject_id)
    return sorted(d for d, custs in device_customers.items() if len(custs) >= 2)


def run(graph, investigate: bool = False) -> dict[str, tuple]:
    """Returns customer_id -> (max_score, tier, verdict_subject)."""
    device_ids = devices_with_sharers(graph)
    customer_best: dict[str, float] = defaultdict(float)

    for i, device_id in enumerate(device_ids, 1):
        verdict = run_risk_for_device(graph, device_id, investigate=investigate)
        for cid in verdict.affected_entities:
            customer_best[cid] = max(customer_best[cid], verdict.decision_score)
        if i % 25 == 0 or i == len(device_ids):
            print(f"  [{i}/{len(device_ids)}] devices scored")

    return customer_best


def print_report(customer_best: dict[str, float], labels: list[dict]) -> bool:
    by_pattern = defaultdict(lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0})
    overall = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}

    for row in labels:
        cid = row["customer_id"]
        is_fraud = row["is_fraud"] == "True"
        pattern = row["pattern"]
        score = customer_best.get(cid, 0.0)
        predicted_fraud = risk_tier(score) == "HIGH"

        bucket = "tp" if (predicted_fraud and is_fraud) else \
                 "fp" if (predicted_fraud and not is_fraud) else \
                 "fn" if (not predicted_fraud and is_fraud) else "tn"
        overall[bucket] += 1
        by_pattern[pattern][bucket] += 1

    def metrics(b):
        precision = b["tp"] / (b["tp"] + b["fp"]) if (b["tp"] + b["fp"]) else float("nan")
        recall = b["tp"] / (b["tp"] + b["fn"]) if (b["tp"] + b["fn"]) else float("nan")
        fpr = b["fp"] / (b["fp"] + b["tn"]) if (b["fp"] + b["tn"]) else float("nan")
        return precision, recall, fpr

    print(f"\n-- Phase 6 Risk report ({len(labels)} customers) --")
    p, r, fpr = metrics(overall)
    print(f"Overall  precision={p:.1%}  recall={r:.1%}  false-positive rate={fpr:.1%}  "
          f"(tp={overall['tp']} fp={overall['fp']} tn={overall['tn']} fn={overall['fn']})")

    print(f"\n{'pattern':<22}{'precision':>11}{'recall':>9}{'fpr':>9}{'tp':>5}{'fp':>5}{'tn':>6}{'fn':>5}")
    for pattern, b in sorted(by_pattern.items()):
        p, r, fpr = metrics(b)
        pstr = f"{p:.1%}" if p == p else "n/a"
        rstr = f"{r:.1%}" if r == r else "n/a"
        fstr = f"{fpr:.1%}" if fpr == fpr else "n/a"
        print(f"{pattern:<22}{pstr:>11}{rstr:>9}{fstr:>9}{b['tp']:>5}{b['fp']:>5}{b['tn']:>6}{b['fn']:>5}")

    benign = by_pattern.get("benign_shared_device", {"fp": 0, "tn": 0})
    benign_fpr = benign["fp"] / (benign["fp"] + benign["tn"]) if (benign["fp"] + benign["tn"]) else float("nan")
    print(f"\nBenign-shared-device false-positive rate: {benign_fpr:.1%} "
          f"({benign['fp']}/{benign['fp']+benign['tn']}) -- the number that proves this isn't "
          f"just 'flag every shared device'")

    ring_recall = by_pattern.get("fraud_ring", {"tp": 0, "fn": 0})
    r_denom = ring_recall["tp"] + ring_recall["fn"]
    print(f"Fraud-ring recall: {ring_recall['tp']}/{r_denom} "
          f"({ring_recall['tp']/r_denom:.1%})" if r_denom else "Fraud-ring recall: n/a")

    return overall["tp"] > 0 and (benign_fpr == 0 or benign_fpr != benign_fpr)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Building graph...")
    state, graph = build_graph()
    labels = load_labels()

    print("Scoring devices...")
    customer_best = run(graph, investigate=False)

    passed = print_report(customer_best, labels)
    print("\nPHASE 6: PASS" if passed else "\nPHASE 6: FAIL")
    sys.exit(0 if passed else 1)
