"""
Phase 7 done check (Phases.md): recovery rate + false-retry rate against
recovery_labels.csv. 4A-only (investigate=False) by default -- Recovery's
whole point is deciding from the category's own base rate, not needing an
LLM call to classify a known failure_reason.

recovery rate = of payments where retry_would_succeed=True (ground truth),
what fraction did Recovery correctly decide to RETRY?
false-retry rate = of Recovery's RETRY decisions, what fraction target a
payment where retry_would_succeed=False? Expected to roughly track
1 - the category's own base_success_rate -- an honest, inherent rate, not a
flaw to eliminate. Recovery can only act on the category's base rate; the
per-instance outcome isn't knowable in advance from anything in this system
(recoverable != should retry).

Run directly: `python -m financial_system.recovery.runner`
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

from financial_system.financial_graph.builder import build_graph
from financial_system.recovery.recovery_agent import run_recovery_for_payment

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "recovery_labels.csv"


def load_labels() -> list[dict]:
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run(graph, labels: list[dict], investigate: bool = False) -> list[dict]:
    records = []
    for i, row in enumerate(labels, 1):
        verdict = run_recovery_for_payment(graph, row["payment_id"], investigate=investigate)
        records.append({
            "payment_id": row["payment_id"], "failure_reason": row["failure_reason"],
            "ground_truth_is_recoverable": row["is_recoverable"] == "True",
            "ground_truth_retry_would_succeed": row["retry_would_succeed"] == "True",
            "decision": verdict.decision, "proposed_action": verdict.proposed_action,
            "decision_score": verdict.decision_score,
            "has_alternate_success": verdict.metrics.get("has_alternate_success", 0.0) > 0,
        })
        if i % 40 == 0 or i == len(labels):
            print(f"  [{i}/{len(labels)}]")
    return records


def print_report(records: list[dict]) -> bool:
    total = len(records)
    retried = [r for r in records if r["decision"] == "RETRY"]
    n_retried = len(retried)

    would_succeed_true = [r for r in records if r["ground_truth_retry_would_succeed"]]
    recovered = sum(1 for r in would_succeed_true if r["decision"] == "RETRY")
    recovery_rate = recovered / len(would_succeed_true) if would_succeed_true else float("nan")

    false_retries = sum(1 for r in retried if not r["ground_truth_retry_would_succeed"])
    false_retry_rate = false_retries / n_retried if n_retried else float("nan")

    category_accuracy = sum(
        1 for r in records
        if (r["decision"] in ("RETRY",)) == r["ground_truth_is_recoverable"] or r["has_alternate_success"]
    ) / total

    print(f"\n-- Phase 7 Recovery report ({total} failed payments) --")
    print(f"Category recoverability accuracy (RETRY decision vs. ground-truth is_recoverable): "
          f"{category_accuracy:.1%}")
    print(f"Recovery rate (of genuinely-would-succeed retries, correctly attempted): "
          f"{recovered}/{len(would_succeed_true)} ({recovery_rate:.1%})")
    print(f"False-retry rate (of attempted retries, would NOT have succeeded): "
          f"{false_retries}/{n_retried} ({false_retry_rate:.1%}) -- expected to roughly track "
          f"1 minus each category's own base_success_rate, not zero")

    print(f"\n{'failure_reason':<24}{'decision':<10}{'n':>5}{'gt_recoverable':>16}{'gt_retry_ok':>13}")
    by_reason = defaultdict(lambda: {"n": 0, "decision": "", "gt_recoverable": 0, "gt_retry_ok": 0})
    for r in records:
        s = by_reason[r["failure_reason"]]
        s["n"] += 1
        s["decision"] = r["decision"]
        s["gt_recoverable"] += r["ground_truth_is_recoverable"]
        s["gt_retry_ok"] += r["ground_truth_retry_would_succeed"]
    for reason, s in sorted(by_reason.items()):
        print(f"{reason:<24}{s['decision']:<10}{s['n']:>5}{s['gt_recoverable']:>16}{s['gt_retry_ok']:>13}")

    n_alt_success = sum(1 for r in records if r["has_alternate_success"])
    print(f"\nalternate-success override triggered: {n_alt_success}/{total} (expected 0 -- each order "
          f"gets exactly one payment attempt in this corpus; the check is real and would fire on a "
          f"real multi-attempt dataset, same 'built but unexercised' pattern as Phase 2's "
          f"probabilistic match and Phase 4's PARTIALLY_EXPLAINED)")

    return category_accuracy > 0.95


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Building graph...")
    state, graph = build_graph()
    labels = load_labels()

    print(f"Running Recovery over {len(labels)} failed payments...")
    records = run(graph, labels, investigate=False)

    passed = print_report(records)
    print("\nPHASE 7: PASS" if passed else "\nPHASE 7: FAIL")
    sys.exit(0 if passed else 1)
