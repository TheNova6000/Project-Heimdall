"""
Simulation -> Heimdall bridge: end-to-end run.

Orchestrates, in order, calling only existing/unmodified financial_system/
functions (parameterized to new paths this package owns -- never the real
financial_system/data/ paths):

  1. simulation_bridge.transform_simulation_output()   [NEW, this package]
       Simulation/<run>/*.csv  ->  bridge_output/raw/*.csv
       (Heimdall's raw-CSV schema, transformed from Simulation's output)

  2. financial_system.financial_state.builder.build_financial_state()  [EXISTING, unmodified]
       Phase 1 ingestion, run exactly as it runs on the real dataset, just
       pointed at bridge_output/raw/ and bridge_output/financial_state.db.

  3. financial_system.entity_resolution.given_matches
       .validate_reference_keys() + .resolve_given_matches()  [EXISTING, unmodified]
       Phase 2's foreign-key-derived matches (Payment<->Order, in particular
       -- what recovery/signals.py's alternate-success check reads). The
       settlement<->bank-transaction probabilistic matcher (Phase 2 step 6)
       and its ground-truth scoring (steps 7-8) are intentionally not
       invoked here: bridged data has no settlements/bank_transactions
       (Simulation/ doesn't model them, see simulation_bridge.py) and no
       ground-truth labels of its own -- scoring zero real candidates
       against financial_system/'s real answer key would be meaningless,
       not a shortcut around anything Recovery needs.

  4. financial_system.financial_graph.builder.build_graph()  [EXISTING, unmodified]
       Phase 3, pointed at the bridge's own state/graph db paths.

  5. financial_system.recovery.recovery_agent.run_recovery_for_payment()  [EXISTING, unmodified]
       Called once per bridged failed Payment -- Heimdall's real, frozen
       Recovery decision logic, running on simulated data for the first
       time. investigate=False (4A-only), same default as recovery/runner.py
       (Phase 7's own done-check), since Discovery.AI/LLM investigation is
       out of scope for this bridge.

  6. financial_system.risk.runner.devices_with_sharers() +
     financial_system.risk.risk_agent.run_risk_for_device()  [EXISTING, unmodified]
       Later addition (see Simulation/docs/Memory.md's "Device" section):
       now that simulation_bridge.py builds devices.csv from Simulation/'s
       REAL Device data (real household-sharing structure, not one
       placeholder per person), Risk's real, unmodified scoring logic can
       run meaningfully on bridged data for the first time. Called on
       every Device with >=2 distinct owning Customers (Risk's own real
       definition of "has any signal to score at all" --
       risk/runner.py's `devices_with_sharers`), investigate=False, same
       4A-only default as risk/runner.py's own Phase 6 done-check.

Run directly: `python -m financial_system.bridges.run_bridge <simulation_outdir> [bridge_outdir]`
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from financial_system.bridges.simulation_bridge import transform_simulation_output
from financial_system.entity_resolution.given_matches import resolve_given_matches, validate_reference_keys
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.builder import build_financial_state
from financial_system.financial_state.store import FinancialStateStore
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.risk.risk_agent import run_risk_for_device
from financial_system.risk.runner import devices_with_sharers

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BRIDGE_DIR = Path(__file__).resolve().parent / "bridge_output"


def run_bridge(sim_outdir: Path, bridge_dir: Path = DEFAULT_BRIDGE_DIR) -> dict:
    bridge_dir = Path(bridge_dir)
    raw_dir = bridge_dir / "raw"
    state_db = bridge_dir / "financial_state.db"
    graph_db = bridge_dir / "financial_graph.db"
    bridge_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/6] transforming Simulation/ output ({sim_outdir}) -> Heimdall raw schema ({raw_dir})")
    transform_report = transform_simulation_output(sim_outdir, raw_dir)
    print(f"      persons={transform_report.persons_read} merchants={transform_report.merchants_read} "
          f"transactions={transform_report.transactions_read} devices={transform_report.devices_read}")
    print(f"      -> orders={transform_report.orders_written} payments={transform_report.payments_written} "
          f"customers={transform_report.customers_written} merchants={transform_report.merchants_written} "
          f"devices(real)={transform_report.devices_written} "
          f"(of which shared by >=2 owners: {transform_report.shared_devices}) "
          f"instruments(fabricated 1:1-per-device wrapper)={transform_report.instruments_written}")
    print(f"      skipped non-purchase transaction kinds: {dict(transform_report.skipped_transaction_kinds)}")

    print(f"\n[2/6] financial_state.builder.build_financial_state() -- Heimdall's real, unmodified Phase 1")
    store, phase1_result = build_financial_state(db_path=state_db, raw_dir=raw_dir)
    print(f"      Phase 1 passed={phase1_result.passed} "
          f"row_count_failures={len(phase1_result.row_count_failures)} "
          f"checksum_failures={len(phase1_result.checksum_failures)}")
    if not phase1_result.passed:
        print(f"      row_count_failures: {phase1_result.row_count_failures}")
        print(f"      checksum_failures: {phase1_result.checksum_failures}")

    print(f"\n[3/6] entity_resolution.given_matches -- Heimdall's real, unmodified Phase 2 (given-matches only)")
    violations = validate_reference_keys(store)
    given = resolve_given_matches(store)
    store.clear_entity_matches()
    for m in given:
        store.add_entity_match(m.subject_type, m.subject_id, m.object_type, m.object_id,
                                m.relation, m.match_method, m.match_score, m.match_evidence,
                                m.source_record_ids)
    store.commit()
    print(f"      reference-key violations: {len(violations)}")
    by_relation = Counter(m.relation for m in given)
    print(f"      given matches persisted: {len(given)} {dict(by_relation)}")

    print(f"\n[4/6] financial_graph.builder.build_graph() -- Heimdall's real, unmodified Phase 3")
    _, graph = build_graph(state_db=state_db, graph_db=graph_db)
    print(f"      node counts: {dict(graph.node_type_counts())}")
    print(f"      edge counts: {dict(graph.relation_counts())}")

    print(f"\n[5/6] recovery.recovery_agent.run_recovery_for_payment() -- Heimdall's real, unmodified Phase 7 "
          f"agent, called on every bridged failed Payment")
    failed_payment_ids = [
        r["payment_id"] for r in store.all_rows("payments") if r["status"] == "failed"
    ]
    decisions = Counter()
    proposed_actions = Counter()
    verdicts = []
    for pid in failed_payment_ids:
        verdict = run_recovery_for_payment(graph, pid, investigate=False)
        decisions[verdict.decision] += 1
        proposed_actions[verdict.proposed_action] += 1
        verdicts.append(verdict)

    print(f"      failed payments: {len(failed_payment_ids)}")
    print(f"      decision distribution: {dict(decisions)}")
    print(f"      proposed_action distribution: {dict(proposed_actions)}")

    print(f"\n[6/6] risk.runner.devices_with_sharers() + risk.risk_agent.run_risk_for_device() -- "
          f"Heimdall's real, unmodified Phase 6 agent, called on every bridged Device with >=2 owners")
    shared_device_ids = devices_with_sharers(graph)
    risk_decisions = Counter()
    risk_verdicts = []
    for device_id in shared_device_ids:
        verdict = run_risk_for_device(graph, device_id, investigate=False)
        risk_decisions[verdict.decision] += 1
        risk_verdicts.append(verdict)

    print(f"      devices with >=2 distinct owning customers: {len(shared_device_ids)}")
    print(f"      decision distribution: {dict(risk_decisions)}")
    if risk_verdicts:
        scores = [v.decision_score for v in risk_verdicts]
        print(f"      decision_score range: {min(scores):.3f} .. {max(scores):.3f}")

    return {
        "transform_report": transform_report,
        "phase1_result": phase1_result,
        "reference_key_violations": violations,
        "given_matches": given,
        "graph": graph,
        "failed_payment_ids": failed_payment_ids,
        "decisions": decisions,
        "proposed_actions": proposed_actions,
        "verdicts": verdicts,
        "shared_device_ids": shared_device_ids,
        "risk_decisions": risk_decisions,
        "risk_verdicts": risk_verdicts,
    }


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m financial_system.bridges.run_bridge <simulation_outdir> [bridge_outdir]")
    sim_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BRIDGE_DIR
    result = run_bridge(sim_dir, out_dir)
    print("\nBRIDGE RUN: COMPLETE")
