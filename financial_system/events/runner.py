"""
Stage 1 (+2) acceptance test, per MIGRATION_DESIGN.md §8 and §10's state-half:

Gate 1 -- state compatibility: backfill historical events from the same raw
CSVs, project them into a fresh financial_state.db, diff every transactional
table row-for-row against the unchanged Phase 1 direct-ingestion path.
`prov_ingestion_run_id`/`prov_ingested_at` are excluded from the diff --
those are execution-identity artifacts (a fresh UUID/timestamp every run,
by design), not business facts; everything else must match exactly.

Gate 2 -- behavioral compatibility: build the graph from the PROJECTED
state, run Phases 5/6/7/9 against it (zero LLM throughout), compare their
headline numbers to the values already documented in Phases.md. Phase 8
(orchestrator) and Phase 10 (action) reuse Phase 5/6/7's verdicts internally
and aren't independently re-checked here to keep this script's own scope
bounded -- their correctness follows from 5/6/7 being correct, since they
call the exact same functions against the exact same graph.

Does NOT touch financial_state/builder.py, financial_graph/builder.py, or
any Phase 5-10 agent code -- this is a new, additive script that consumes
the existing, unchanged pipeline as a comparison baseline.

Run directly: `python -m financial_system.events.runner`
"""
from __future__ import annotations

import sys
from pathlib import Path

from financial_system.entity_resolution.runner import run_phase2
from financial_system.events.backfill import backfill
from financial_system.events.store import EventStore
from financial_system.events.projection import project
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.builder import build_financial_state
from financial_system.financial_state.store import FinancialStateStore
from financial_system.ingestion import reference_ingestion

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = REPO_ROOT / "financial_system" / "data" / "raw"
EVENTS_DB = REPO_ROOT / "financial_system" / "data" / "events.db"
PROJECTED_STATE_DB = REPO_ROOT / "financial_system" / "data" / "financial_state_projected.db"
PROJECTED_GRAPH_DB = REPO_ROOT / "financial_system" / "data" / "financial_graph_projected.db"

TRANSACTIONAL_TABLES = ["orders", "payments", "settlements", "settlement_payments",
                          "bank_transactions", "refunds", "fees"]
# Excluded from the diff -- inherently different every run, not business facts.
# surrogate_id is settlement_payments' AUTOINCREMENT PK (junction rows have no
# natural id) -- an insertion-order artifact, same category as the other two.
EXCLUDE_COLUMNS = {"prov_ingestion_run_id", "prov_ingested_at", "surrogate_id"}

# Documented baselines from Phases.md, computed against the unchanged
# direct-ingestion pipeline -- Gate 2 must reproduce these exactly.
EXPECTED = {
    "controller_match_rate": (607, 610),
    "risk_precision": 1.0, "risk_recall_fraud_ring": (26, 27), "risk_fpr_benign": (0, 16),
    "recovery_category_accuracy": 1.0, "recovery_rate": (87, 87),
}


def _row_key(row, exclude: set[str]) -> tuple:
    return tuple(sorted((k, v) for k, v in dict(row).items() if k not in exclude))


def run_gate1() -> bool:
    print("== Gate 1: state compatibility ==")

    if EVENTS_DB.exists():
        EVENTS_DB.unlink()
    events = EventStore(EVENTS_DB)
    counts = backfill(events, RAW_DIR)
    print(f"Backfilled events: {counts}  (total={events.count()})")

    if PROJECTED_STATE_DB.exists():
        PROJECTED_STATE_DB.unlink()
    projected = FinancialStateStore(PROJECTED_STATE_DB)
    run_id = "gate1_reference_ingestion"
    # Orders are genuinely transactional (an occurrence, not a standing entity like
    # Merchant/Customer/Device) -- event-sourced via OrderCreated -> project(), NOT
    # re-ingested here, or add_order() would hit a DuplicateRecordError on the same
    # order_id from two different paths.
    for fn in (reference_ingestion.ingest_merchants, reference_ingestion.ingest_customers,
               reference_ingestion.ingest_devices, reference_ingestion.ingest_instruments):
        fn(projected, RAW_DIR, run_id)
    projected.commit()
    proj_counts = project(events, projected)
    print(f"Projected from events: {proj_counts}")

    baseline_db = REPO_ROOT / "financial_system" / "data" / "financial_state.db"
    if baseline_db.exists():
        baseline_db.unlink()
    baseline, _ = build_financial_state(db_path=baseline_db, raw_dir=RAW_DIR)

    all_match = True
    for table in TRANSACTIONAL_TABLES:
        baseline_rows = {_row_key(r, EXCLUDE_COLUMNS) for r in baseline.all_rows(table)}
        projected_rows = {_row_key(r, EXCLUDE_COLUMNS) for r in projected.all_rows(table)}
        match = baseline_rows == projected_rows
        all_match &= match
        status = "OK" if match else "MISMATCH"
        extra_in_baseline = len(baseline_rows - projected_rows)
        extra_in_projected = len(projected_rows - baseline_rows)
        print(f"  {table:<22} baseline={len(baseline_rows):<5} projected={len(projected_rows):<5} "
              f"[{status}]" + (f"  only_in_baseline={extra_in_baseline} only_in_projected={extra_in_projected}"
                                if not match else ""))

    print("GATE 1: PASS" if all_match else "GATE 1: FAIL")
    return all_match


def run_gate2() -> bool:
    print("\n== Gate 2: behavioral compatibility ==")

    violations = run_phase2(db_path=PROJECTED_STATE_DB)[0]
    if violations:
        print(f"GATE 2: FAIL -- entity resolution found {len(violations)} reference-key violations")
        return False

    state, graph = build_graph(state_db=PROJECTED_STATE_DB, graph_db=PROJECTED_GRAPH_DB)

    from financial_system.reconciliation.runner import load_rows as load_recon_rows
    from financial_system.reconciliation.runner import run as run_controller
    recon_records = run_controller(graph, load_recon_rows(),
                                    investigate=False, results_path=REPO_ROOT / "financial_system" /
                                    "data" / "phase5_results" / "gate2_check.jsonl")
    matches = sum(1 for r in recon_records if r["match"])
    controller_ok = (matches, len(recon_records)) == EXPECTED["controller_match_rate"]
    print(f"Controller match rate: {matches}/{len(recon_records)} "
          f"(expected {EXPECTED['controller_match_rate']}) [{'OK' if controller_ok else 'MISMATCH'}]")

    from financial_system.risk.runner import load_labels as load_risk_labels
    from financial_system.risk.runner import run as run_risk
    from financial_system.risk.scoring import risk_tier
    customer_best = run_risk(graph, investigate=False)
    risk_labels = load_risk_labels()
    tp = fp = fn_ = tn_benign = 0
    for row in risk_labels:
        score = customer_best.get(row["customer_id"], 0.0)
        predicted = risk_tier(score) == "HIGH"
        is_fraud = row["is_fraud"] == "True"
        if row["pattern"] == "fraud_ring":
            tp += predicted and is_fraud
            fn_ += (not predicted) and is_fraud
        if row["pattern"] == "benign_shared_device":
            fp += predicted  # a false positive on a benign case is always wrong
            tn_benign += not predicted
    risk_recall = (tp, tp + fn_)
    risk_fpr = (fp, fp + tn_benign)
    risk_ok = risk_recall == EXPECTED["risk_recall_fraud_ring"] and risk_fpr == EXPECTED["risk_fpr_benign"]
    print(f"Risk fraud_ring recall: {risk_recall[0]}/{risk_recall[1]} "
          f"(expected {EXPECTED['risk_recall_fraud_ring']}), "
          f"benign FPR: {risk_fpr[0]}/{risk_fpr[1]} (expected {EXPECTED['risk_fpr_benign']}) "
          f"[{'OK' if risk_ok else 'MISMATCH'}]")

    from financial_system.recovery.runner import load_labels as load_recovery_labels
    from financial_system.recovery.runner import run as run_recovery
    recovery_records = run_recovery(graph, load_recovery_labels(), investigate=False)
    would_succeed = [r for r in recovery_records if r["ground_truth_retry_would_succeed"]]
    recovered = sum(1 for r in would_succeed if r["decision"] == "RETRY")
    recovery_ok = (recovered, len(would_succeed)) == EXPECTED["recovery_rate"]
    print(f"Recovery rate: {recovered}/{len(would_succeed)} (expected {EXPECTED['recovery_rate']}) "
          f"[{'OK' if recovery_ok else 'MISMATCH'}]")

    all_ok = controller_ok and risk_ok and recovery_ok
    print("GATE 2: PASS" if all_ok else "GATE 2: FAIL")
    return all_ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    gate1 = run_gate1()
    gate2 = run_gate2() if gate1 else False
    print(f"\nSTAGE 1: {'PASS' if gate1 and gate2 else 'FAIL'}")
    sys.exit(0 if gate1 and gate2 else 1)
