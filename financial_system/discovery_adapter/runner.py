"""
Phase 4 runner: builds/loads the graph, runs open_investigation() against every
settlement-level exception in the ground truth, and reports 4A's measured
accuracy -- not a handful of eyeballed examples. If has_any_provider_key() is
True, every one of these also executes 4B for real; the report says which mode
actually ran.

missing_settlement rows are excluded from scoring: that anomaly means there is
no Settlement node to investigate in the first place (Phase 4 investigates a
NAMED settlement; discovering "this payment has no settlement at all" is a
sweep over all payments, which is Phase 5 Controller's job, not Phase 4's).

Run directly: `python -m financial_system.discovery_adapter.runner`
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

from financial_system.discovery_adapter.investigate import open_investigation
from financial_system.discovery_adapter.models import InvestigationRequest
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_graph.repository import GraphRepository

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "reconciliation_labels.csv"


def _load_labels() -> list[dict]:
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["root_cause"] != "missing_settlement"]


def run_phase4(graph: GraphRepository, labels: list[dict]) -> dict:
    results_by_cause = defaultdict(lambda: {"correct": 0, "total": 0, "mismatches": []})
    executed_4b_count = 0

    for row in labels:
        request = InvestigationRequest(
            subject_type="Settlement", subject_id=row["settlement_id"],
            question_text=f"Why does settlement {row['settlement_id']}'s recorded net amount "
                          f"differ from what the bank actually deposited?",
        )
        result = open_investigation(request, graph)
        if result.executed_4b:
            executed_4b_count += 1

        expected_explainable = row["is_explainable"] == "True"
        predicted_explainable = result.status.value == "EXPLAINED"

        cause = row["root_cause"]
        results_by_cause[cause]["total"] += 1
        if predicted_explainable == expected_explainable:
            results_by_cause[cause]["correct"] += 1
        else:
            results_by_cause[cause]["mismatches"].append(
                f"{row['settlement_id']}: ground_truth={expected_explainable}, "
                f"predicted={predicted_explainable} (status={result.status.value})")

    return {"by_cause": dict(results_by_cause), "executed_4b_count": executed_4b_count,
            "total": len(labels)}


def _print_report(report: dict):
    print(f"-- Phase 4A: reconciliation exception classification, {report['total']} settlements --")
    print(f"{'root_cause':<20}{'correct':>10}{'total':>8}{'accuracy':>10}")
    total_correct = 0
    for cause, stats in sorted(report["by_cause"].items()):
        acc = stats["correct"] / stats["total"] if stats["total"] else 0.0
        total_correct += stats["correct"]
        print(f"{cause:<20}{stats['correct']:>10}{stats['total']:>8}{acc:>10.1%}")
        if stats["mismatches"]:
            print(f"    mismatches: {stats['mismatches'][:2]}")
    print(f"{'TOTAL':<20}{total_correct:>10}{report['total']:>8}{total_correct/report['total']:>10.1%}")

    print()
    if report["executed_4b_count"]:
        print(f"4B executed for real on {report['executed_4b_count']}/{report['total']} investigations "
              f"(LLM provider key was configured)")
    else:
        print("4B did not execute for any investigation -- no LLM provider key configured. "
              "This report is 4A-only (deterministic reconciliation, zero LLM calls).")


if __name__ == "__main__":
    state, graph = build_graph()  # rebuilds the graph fresh, same reproducibility rule as prior phases
    labels = _load_labels()
    report = run_phase4(graph, labels)
    _print_report(report)
    sys.exit(0)
