"""
Phase 5 done check (Phases.md): match rate + honest-exception rate against
reconciliation_labels.csv, printed as numbers.

4A-only by default -- Controller's whole point is not calling Discovery.AI for
cases it can already resolve itself, so a plain run costs zero LLM quota.
Pass --investigate to let genuinely UNEXPLAINED cases actually call 4B (only
those, never the ones Controller already resolved).

missing_settlement rows excluded: that anomaly means no Settlement node
exists to run Controller against in the first place -- a sweep over
unsettled-but-successful payments, not something Controller decides on a
per-settlement basis. Same treatment as Phase 4.

Run directly: `python -m financial_system.reconciliation.runner [--investigate]`
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from financial_system.financial_graph.builder import build_graph
from financial_system.reconciliation.controller import run_controller_for_settlement

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "reconciliation_labels.csv"
RESULTS_DIR = REPO_ROOT / "financial_system" / "data" / "phase5_results"

_RESOLVED_DECISIONS = {"PASS", "RESOLVE"}


def load_rows() -> list[dict]:
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["root_cause"] != "missing_settlement"]


def run(graph, rows: list[dict], investigate: bool, results_path: Path) -> list[dict]:
    import json
    records = []
    for i, row in enumerate(rows, 1):
        verdict = run_controller_for_settlement(graph, row["settlement_id"], investigate=investigate)
        expected_explainable = row["is_explainable"] == "True"
        predicted_resolved = verdict.decision in _RESOLVED_DECISIONS
        record = {
            "settlement_id": row["settlement_id"], "root_cause": row["root_cause"],
            "expected_explainable": expected_explainable, "decision": verdict.decision,
            "predicted_resolved": predicted_resolved, "match": predicted_resolved == expected_explainable,
            "investigated": verdict.investigation_id is not None,
        }
        records.append(record)
        results_path.parent.mkdir(parents=True, exist_ok=True)
        with open(results_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({**record, "reason": verdict.reason}) + "\n")
        if i % 50 == 0 or i == len(rows):
            print(f"  [{i}/{len(rows)}]")
    return records


def print_report(records: list[dict]) -> bool:
    total = len(records)
    matches = sum(1 for r in records if r["match"])
    match_rate = matches / total if total else 0.0

    unexplainable = [r for r in records if not r["expected_explainable"]]
    honest = sum(1 for r in unexplainable if not r["predicted_resolved"])
    honest_rate = honest / len(unexplainable) if unexplainable else 0.0

    print(f"\n-- Phase 5 Controller report ({total} settlements) --")
    print(f"Match rate (decision matches ground-truth is_explainable):     {matches}/{total} ({match_rate:.1%})")
    print(f"Honest-exception rate (genuinely unexplainable, correctly not"
          f" resolved): {honest}/{len(unexplainable)} ({honest_rate:.1%})")

    by_cause = defaultdict(lambda: {"match": 0, "total": 0})
    for r in records:
        by_cause[r["root_cause"]]["total"] += 1
        by_cause[r["root_cause"]]["match"] += r["match"]
    print(f"\n{'root_cause':<20}{'match':>8}{'total':>8}")
    for cause, s in sorted(by_cause.items()):
        print(f"{cause:<20}{s['match']:>8}{s['total']:>8}")

    n_investigated = sum(1 for r in records if r["investigated"])
    print(f"\ninvestigated (4B actually called): {n_investigated}/{total}")

    mismatches = [r for r in records if not r["match"]]
    if mismatches:
        print(f"\nmismatches (first 5): {[m['settlement_id'] for m in mismatches[:5]]}")

    return match_rate >= 0.95


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    investigate = "--investigate" in sys.argv

    print("Building graph...")
    state, graph = build_graph()
    rows = load_rows()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results_path = RESULTS_DIR / f"controller_{run_id}.jsonl"
    print(f"Running Controller over {len(rows)} settlements "
          f"(investigate={investigate}), persisting to {results_path}...")

    records = run(graph, rows, investigate, results_path)
    passed = print_report(records)
    print("\nPHASE 5: PASS" if passed else "\nPHASE 5: FAIL")
    sys.exit(0 if passed else 1)
