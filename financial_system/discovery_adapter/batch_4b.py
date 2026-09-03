"""
Phase 4B batch runner: real LLM calls, streaming every case to a JSONL file as
it completes (survives a rate-limit-induced interruption), then a full
automatic summary from the persisted records -- not hand-grepped log lines.

Run directly: `python -m financial_system.discovery_adapter.batch_4b [--full] [--per-cause N]`
`--full` runs all non-missing_settlement rows; default is a stratified sample.
"""
from __future__ import annotations

import csv
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from financial_system.discovery_adapter.investigate import open_investigation
from financial_system.discovery_adapter.models import InvestigationRequest
from financial_system.discovery_adapter.persistence import append_case_record, build_case_record, load_case_records
from financial_system.financial_graph.builder import build_graph

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "reconciliation_labels.csv"
RESULTS_DIR = REPO_ROOT / "financial_system" / "data" / "phase4_results"
SEED = 42


def load_rows() -> list[dict]:
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["root_cause"] != "missing_settlement"]


def pick_stratified_sample(rows: list[dict], per_cause: int) -> list[dict]:
    by_cause = defaultdict(list)
    for r in rows:
        by_cause[r["root_cause"]].append(r)
    rng = random.Random(SEED)
    sample = []
    for cause, group in sorted(by_cause.items()):
        sample.extend(rng.sample(group, min(per_cause, len(group))))
    return sample


def run_batch(graph, sample: list[dict], results_path: Path) -> None:
    for i, row in enumerate(sample, 1):
        request = InvestigationRequest(
            subject_type="Settlement", subject_id=row["settlement_id"],
            question_text=f"Why does settlement {row['settlement_id']}'s recorded net amount "
                          f"differ from what the bank actually deposited?",
        )
        result = open_investigation(request, graph)
        record = build_case_record(row["settlement_id"], row["root_cause"],
                                    row["is_explainable"] == "True", result)
        append_case_record(results_path, record)
        print(f"[{i}/{len(sample)}] {row['settlement_id']} ({row['root_cause']}): "
              f"status={result.status.value} confidence={result.investigation_confidence} "
              f"correct={record['correct']} grounded={record['validation']['numeric_grounding_ok']} "
              f"resources={result.resources_used}/{result.resources_offered}")


def print_summary(records: list[dict]) -> None:
    print("\n" + "=" * 80)
    print(f"-- Phase 4B batch summary ({len(records)} cases) --")

    by_cause = defaultdict(list)
    for r in records:
        by_cause[r["root_cause"]].append(r)

    n_4b = sum(1 for r in records if r["4B"]["executed"])
    print(f"4B executed: {n_4b}/{len(records)}")

    print(f"\n{'root_cause':<20}{'correct':>10}{'total':>8}{'avg_conf':>10}{'ungrounded':>12}")
    for cause, group in sorted(by_cause.items()):
        correct = sum(1 for r in group if r["correct"])
        confs = [r["4B"]["confidence"] for r in group if r["4B"]["confidence"] is not None]
        avg_conf = f"{sum(confs)/len(confs):.2f}" if confs else "n/a"
        ungrounded = sum(1 for r in group if not r["validation"]["numeric_grounding_ok"])
        print(f"{cause:<20}{correct:>10}{len(group):>8}{avg_conf:>10}{ungrounded:>12}")

    explained_conf = [r["4B"]["confidence"] for r in records
                       if r["4A"]["status"] == "EXPLAINED" and r["4B"]["confidence"] is not None]
    unexplained_conf = [r["4B"]["confidence"] for r in records
                         if r["4A"]["status"] == "UNEXPLAINED" and r["4B"]["confidence"] is not None]
    if explained_conf and unexplained_conf:
        print(f"\navg confidence when EXPLAINED:   {sum(explained_conf)/len(explained_conf):.2f} (n={len(explained_conf)})")
        print(f"avg confidence when UNEXPLAINED: {sum(unexplained_conf)/len(unexplained_conf):.2f} (n={len(unexplained_conf)})")

    hallucinations = [r for r in records if r["validation"]["hallucination_flags"]]
    print(f"\nhallucination flags (ungrounded number backing a non-UNEXPLAINED result): {len(hallucinations)}")
    for r in hallucinations[:5]:
        print(f"  {r['settlement_id']}: {r['validation']['hallucination_flags']}")

    partial = sum(1 for r in records if r["4A"]["status"] == "PARTIALLY_EXPLAINED")
    print(f"\nPARTIALLY_EXPLAINED occurrences: {partial}")

    latencies = [r["llm"]["latency_seconds"] for r in records if r["llm"]["latency_seconds"] is not None]
    fallbacks = sum(r["llm"]["fallback_events"] for r in records)
    failures = sum(r["llm"]["full_failures"] for r in records)
    resources_used = [r["4B"]["resources_used"] for r in records if r["4B"]["executed"]]
    resources_offered = [r["4B"]["resources_offered"] for r in records if r["4B"]["executed"]]
    if latencies:
        print(f"\ntotal 4B latency: {sum(latencies):.1f}s across {len(latencies)} investigations "
              f"(avg {sum(latencies)/len(latencies):.1f}s each)")
    print(f"total fallback_events: {fallbacks}, total full_failures: {failures}")
    if resources_used:
        print(f"resources offered avg: {sum(resources_offered)/len(resources_offered):.1f}, "
              f"resources used avg: {sum(resources_used)/len(resources_used):.1f} "
              f"(max_results cap now enforced)")

    providers = defaultdict(int)
    for r in records:
        for p in r["llm"]["providers_seen"]:
            providers[p] += 1
    if providers:
        print(f"\nprovider appearance count (in failure logs, not a full utilization picture): "
              f"{dict(providers)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    full = "--full" in sys.argv
    per_cause = 5
    if "--per-cause" in sys.argv:
        per_cause = int(sys.argv[sys.argv.index("--per-cause") + 1])

    print("Building graph...")
    state, graph = build_graph()
    rows = load_rows()
    sample = rows if full else pick_stratified_sample(rows, per_cause)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results_path = RESULTS_DIR / f"batch_{'full' if full else 'sample'}_{run_id}.jsonl"
    print(f"Running {len(sample)} real investigation(s), persisting to {results_path}...\n")

    run_batch(graph, sample, results_path)
    records = load_case_records(results_path)
    print_summary(records)
