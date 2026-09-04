"""
Runs all 4 verification checks (replay correctness, temporal integrity,
evidence grounding, idempotency -- see replay.py/temporal.py/grounding.py/
idempotency.py) against TWO real, independently-produced sets of
`AgentVerdict`s:

  1. The real Heimdall dataset (financial_system/data/): Risk + Recovery +
     Controller verdicts, produced by calling the same real, unmodified
     agent functions risk/runner.py, recovery/runner.py, and
     reconciliation/runner.py themselves call.
  2. A bridged Truman (Simulation/) run, via
     financial_system/bridges/run_bridge.py's real, unmodified
     `run_bridge()` -- proving this verification engine is genuinely
     domain/source-agnostic, not hardcoded to one dataset's shape.

Every db file this script writes (replay-correctness rebuilds, the
bridge's own state/graph dbs) goes under a caller-supplied `work_dir`,
never under financial_system/data/ or financial_system/bridges/
bridge_output/ -- this script only ever READS the real dataset's existing
financial_state.db/financial_graph.db (rebuilding financial_graph.db in
place is exactly what risk/runner.py, recovery/runner.py, and
reconciliation/runner.py already do themselves on every run; this script
does nothing to financial_system/data/ that those don't already do).

Run directly: `python -m financial_system.verification.run_verification [work_dir] [sim_outdir]`
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

from financial_system.bridges.run_bridge import run_bridge
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.builder import RAW_DIR as REAL_RAW_DIR
from financial_system.reconciliation.controller import run_controller_for_settlement
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.risk.risk_agent import run_risk_for_device
from financial_system.risk.runner import devices_with_sharers
from financial_system.verification import report as report_mod
from financial_system.verification.grounding import check_evidence_grounding
from financial_system.verification.idempotency import check_idempotency
from financial_system.verification.replay import verify_replay_correctness
from financial_system.verification.temporal import check_temporal_integrity

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SIM_OUTDIR = REPO_ROOT / "Simulation" / "output" / "bridge_run_controller"


def _collect_risk_verdicts(graph):
    device_ids = devices_with_sharers(graph)
    return device_ids, [run_risk_for_device(graph, d, investigate=False) for d in device_ids]


def _collect_recovery_verdicts(state, graph):
    failed_payment_ids = [r["payment_id"] for r in state.all_rows("payments") if r["status"] == "failed"]
    return failed_payment_ids, [run_recovery_for_payment(graph, pid, investigate=False) for pid in failed_payment_ids]


def _collect_controller_verdicts(state, graph):
    settlement_ids = [r["settlement_id"] for r in state.all_rows("settlements")]
    return settlement_ids, [run_controller_for_settlement(graph, sid, investigate=False) for sid in settlement_ids]


def _temporal_audit_risk(graph, device_ids: list[str]) -> list:
    """Same real production code path risk/temporal_runner.py already
    benchmarks: score each device as-of EACH payment observed on it, using
    that payment's own created_at as the decision's effective as-of time
    (risk/risk_agent.py::run_risk_for_device(..., as_of=...) ->
    risk/signals.py::compute_device_risk_signals(..., as_of=...) ->
    financial_graph/queries.py::edges_to_as_of). Then audit each resulting
    verdict against that same as_of."""
    results = []
    for device_id in device_ids:
        payment_edges = graph.edges_to(device_id, "used_device")
        for e in payment_edges:
            payment = graph.get_node(e.subject_id)
            if not payment:
                continue
            as_of = datetime.fromisoformat(payment.properties["created_at"])
            verdict = run_risk_for_device(graph, device_id, investigate=False, as_of=as_of)
            results.append(check_temporal_integrity(graph, verdict, as_of))
    return results


def _idempotency_checks(graph, risk_device_ids, recovery_payment_ids, settlement_ids) -> list:
    results = []
    if risk_device_ids:
        results.append(check_idempotency(run_risk_for_device, graph, risk_device_ids[0], investigate=False))
    if recovery_payment_ids:
        results.append(check_idempotency(run_recovery_for_payment, graph, recovery_payment_ids[0], investigate=False))
    if settlement_ids:
        results.append(check_idempotency(run_controller_for_settlement, graph, settlement_ids[0], investigate=False))
    return results


def run_real_dataset_checks(work_dir: Path) -> tuple[str, str, list]:
    print("=== REAL HEIMDALL DATASET ===")
    print("Building graph (financial_system.financial_graph.builder.build_graph(), real, unmodified)...")
    state, graph = build_graph()

    print("Collecting Risk verdicts (risk.risk_agent.run_risk_for_device, real, unmodified)...")
    risk_device_ids, risk_verdicts = _collect_risk_verdicts(graph)
    print(f"  {len(risk_verdicts)} Risk verdicts")

    print("Collecting Recovery verdicts (recovery.recovery_agent.run_recovery_for_payment, real, unmodified)...")
    recovery_payment_ids, recovery_verdicts = _collect_recovery_verdicts(state, graph)
    print(f"  {len(recovery_verdicts)} Recovery verdicts")

    print("Collecting Controller verdicts (reconciliation.controller.run_controller_for_settlement, "
          "real, unmodified)...")
    settlement_ids, controller_verdicts = _collect_controller_verdicts(state, graph)
    print(f"  {len(controller_verdicts)} Controller verdicts")

    print("Check 1/4 -- Replay correctness (rebuilding financial_state.db twice from the real raw CSVs)...")
    replay_result = verify_replay_correctness(REAL_RAW_DIR, n_replays=2, work_dir=work_dir / "replay")
    print(f"  identical={replay_result.identical}")

    print("Check 2/4 -- Temporal integrity (Risk's real as-of mechanism, every observed payment)...")
    temporal_results = _temporal_audit_risk(graph, risk_device_ids)
    print(f"  {len(temporal_results)} as-of-scoped Risk decisions audited")

    print("Check 3/4 -- Evidence grounding (all three domains)...")
    grounding_results = [
        check_evidence_grounding(graph, risk_verdicts),
        check_evidence_grounding(graph, recovery_verdicts),
        check_evidence_grounding(graph, controller_verdicts),
    ]

    print("Check 4/4 -- Idempotency (one real subject per domain)...")
    idempotency_results = _idempotency_checks(graph, risk_device_ids, recovery_payment_ids, settlement_ids)

    checks = [
        report_mod.summarize_replay(replay_result),
        report_mod.summarize_temporal("risk", temporal_results),
        report_mod.summarize_grounding(grounding_results),
        report_mod.summarize_idempotency(idempotency_results),
    ]
    intro = (
        f"Real Heimdall dataset (`financial_system/data/`): {len(risk_verdicts)} Risk verdicts "
        f"(devices with >=2 sharing customers), {len(recovery_verdicts)} Recovery verdicts (failed "
        f"payments), {len(controller_verdicts)} Controller verdicts (settlements)."
    )
    return "Source 1: Real Heimdall dataset", intro, checks


def run_bridged_checks(sim_outdir: Path, work_dir: Path) -> tuple[str, str, list]:
    print("\n=== BRIDGED TRUMAN (Simulation/) RUN ===")
    bridge_dir = work_dir / "bridge_output"
    print(f"Running financial_system.bridges.run_bridge.run_bridge({sim_outdir}, {bridge_dir}) "
          f"(real, unmodified bridge)...")
    result = run_bridge(sim_outdir, bridge_dir)
    graph = result["graph"]
    risk_verdicts = result["risk_verdicts"]
    recovery_verdicts = result["verdicts"]
    controller_verdicts = result["controller_verdicts"]
    risk_device_ids = result["shared_device_ids"]
    recovery_payment_ids = result["failed_payment_ids"]
    settlement_ids = result["settlement_ids"]

    print("\nCheck 1/4 -- Replay correctness (rebuilding the bridge's transformed raw CSVs twice)...")
    bridge_raw_dir = bridge_dir / "raw"
    replay_result = verify_replay_correctness(bridge_raw_dir, n_replays=2, work_dir=work_dir / "replay_bridged")
    print(f"  identical={replay_result.identical}")

    print("Check 2/4 -- Temporal integrity (Risk's real as-of mechanism, bridged data)...")
    temporal_results = _temporal_audit_risk(graph, risk_device_ids)
    print(f"  {len(temporal_results)} as-of-scoped Risk decisions audited")

    print("Check 3/4 -- Evidence grounding (all three domains, bridged data)...")
    grounding_results = [
        check_evidence_grounding(graph, risk_verdicts),
        check_evidence_grounding(graph, recovery_verdicts),
        check_evidence_grounding(graph, controller_verdicts),
    ]

    print("Check 4/4 -- Idempotency (one real subject per domain, bridged data)...")
    idempotency_results = _idempotency_checks(graph, risk_device_ids, recovery_payment_ids, settlement_ids)

    checks = [
        report_mod.summarize_replay(replay_result),
        report_mod.summarize_temporal("risk", temporal_results),
        report_mod.summarize_grounding(grounding_results),
        report_mod.summarize_idempotency(idempotency_results),
    ]
    intro = (
        f"Bridged Truman (`Simulation/`) run (`{sim_outdir}` via `financial_system/bridges/run_bridge.py`, "
        f"real, unmodified): {len(risk_verdicts)} Risk verdicts, {len(recovery_verdicts)} Recovery "
        f"verdicts, {len(controller_verdicts)} Controller verdicts. Proves this verification engine is "
        f"genuinely domain/source-agnostic, not hardcoded to the real dataset's shape."
    )
    return "Source 2: Bridged Truman (Simulation/) run", intro, checks


def main(work_dir: Path, sim_outdir: Path) -> str:
    work_dir.mkdir(parents=True, exist_ok=True)
    real_section = run_real_dataset_checks(work_dir / "real")
    bridged_section = run_bridged_checks(sim_outdir, work_dir / "bridged")
    report_text = report_mod.build_report(
        "Heimdall Verification Engine -- Report (NORTH_STAR.md Section 24)",
        [real_section, bridged_section],
    )
    return report_text


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # Default work_dir is a disposable system-temp directory, deliberately
    # OUTSIDE financial_system/ -- this module's own source is the only
    # thing meant to land under financial_system/verification/; the
    # sqlite dbs a run produces (replay rebuilds, the bridge's own
    # state/graph dbs) are scratch, not part of the module.
    work_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="heimdall_verification_"))
    sim_outdir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_SIM_OUTDIR
    report_text = main(work_dir, sim_outdir)
    print("\n\n" + report_text)
    print(f"\n(scratch dbs for this run under: {work_dir})")
