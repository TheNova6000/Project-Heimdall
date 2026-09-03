"""
Phase 4B smoke test: a handful of REAL investigations (real LLM calls), picked
to cover the interesting cases -- not the full 610-settlement batch, to avoid
burning quota before we know the wiring actually works end to end.

Prints the full InvestigationResult for each, including Discovery.AI's own
decision, narrative, confidence, and hypotheses -- so a human can eyeball
whether it's actually reasoning over our financial world or just producing
plausible-sounding noise.

Run directly: `python -m financial_system.discovery_adapter.smoke_test`
"""
from __future__ import annotations

import csv
from pathlib import Path

from financial_system.discovery_adapter.investigate import open_investigation
from financial_system.discovery_adapter.models import InvestigationRequest
from financial_system.financial_graph.builder import build_graph

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "reconciliation_labels.csv"

# One of each interesting shape: a case 4A already fully explains (duplicate_record),
# two genuinely unexplainable cases (bank_adjustment, currency_conversion -- the real
# test of "does it refuse to hallucinate a cause"), and one clean/normal settlement.
SAMPLE_ROOT_CAUSES = ["duplicate_record", "bank_adjustment", "currency_conversion", "none"]


def pick_samples() -> list[dict]:
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    picked = []
    for cause in SAMPLE_ROOT_CAUSES:
        row = next((r for r in rows if r["root_cause"] == cause), None)
        if row:
            picked.append(row)
    return picked


def _print_result(row: dict, result) -> None:
    print("=" * 80)
    print(f"settlement={row['settlement_id']}  ground_truth_root_cause={row['root_cause']}  "
          f"ground_truth_is_explainable={row['is_explainable']}")
    print(f"STATUS: {result.status.value}")
    print(f"expected={result.expected_amount}  actual={result.actual_amount}  "
          f"unexplained={result.unexplained_amount}")
    print(f"executed_4b={result.executed_4b}")
    if result.executed_4b:
        print(f"  Discovery.AI decide_next_step action: {result.ground_decision_action}")
        print(f"  hypotheses (per-resource claims):")
        for h in result.hypotheses:
            print(f"    - {h}")
        print(f"  narrative: {result.narrative}")
        print(f"  investigation_confidence: {result.investigation_confidence}")
    if result.execution_note:
        print(f"note: {result.execution_note}")
    print(f"facts ({len(result.facts)}):")
    for f in result.facts:
        print(f"  - {f}")


if __name__ == "__main__":
    import sys
    # Windows' default console codepage (cp1252) can't encode characters an LLM
    # commonly produces (curly quotes, narrow no-break spaces) -- Discovery.AI's
    # own codebase hit this exact class of bug before (Architecture.md's
    # non-breaking-hyphen finding in the provider fallback handler). Force UTF-8
    # on stdout rather than crash mid-print.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Building graph...")
    state, graph = build_graph()

    samples = pick_samples()
    print(f"Running {len(samples)} real investigation(s)...\n")

    for row in samples:
        request = InvestigationRequest(
            subject_type="Settlement", subject_id=row["settlement_id"],
            question_text=f"Why does settlement {row['settlement_id']}'s recorded net amount "
                          f"differ from what the bank actually deposited?",
        )
        result = open_investigation(request, graph)
        _print_result(row, result)
