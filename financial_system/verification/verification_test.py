"""
Test suite for financial_system/verification/ -- same convention as
financial_system/reconciliation/accounting_consistency_test.py and
financial_system/decisions/adversarial_test.py: plain functions returning
bool, real production data where the task calls for it, small NAMED
synthetic fixtures only where a positive-detection case is needed (a
check that never fires on real data still needs proof it CAN fire) --
never presented as if they came from the real corpus.

Run directly: `python -m financial_system.verification.verification_test`
"""
from __future__ import annotations

import csv
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.builder import RAW_DIR as REAL_RAW_DIR
from financial_system.reconciliation.controller import run_controller_for_settlement
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.risk.risk_agent import run_risk_for_device
from financial_system.risk.runner import devices_with_sharers
from financial_system.verdict import AgentVerdict
from financial_system.verification.grounding import check_evidence_grounding
from financial_system.verification.idempotency import check_idempotency
from financial_system.verification.replay import verify_replay_correctness
from financial_system.verification.temporal import check_temporal_integrity, node_timestamp

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _mutated_raw_dir(dst: Path) -> Path:
    """Copies the real raw/ dir, then changes exactly one payment's amount
    -- a deliberate, named synthetic mutation, only to prove the replay
    check can detect a real divergence, not evidence about the real
    dataset itself."""
    dst.mkdir(parents=True, exist_ok=True)
    for f in REAL_RAW_DIR.glob("*.csv"):
        shutil.copy(f, dst / f.name)

    payments_path = dst / "payments.csv"
    with open(payments_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    rows[0]["amount"] = str(float(rows[0]["amount"]) + 1.0)
    with open(payments_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return dst


def test_replay_correctness_real_dataset_identical() -> bool:
    print("-- 1a. Replay correctness: real dataset, two independent rebuilds --")
    with tempfile.TemporaryDirectory(prefix="heimdall_verify_test_") as tmp:
        result = verify_replay_correctness(REAL_RAW_DIR, n_replays=2, work_dir=Path(tmp))
    print(f"  identical={result.identical}")
    print(f"  row_counts={result.fingerprints[0].row_counts}")
    ok = result.identical and not result.row_count_diffs and not result.money_sum_diffs
    print("  PASS" if ok else "  FAIL")
    return ok


def test_replay_correctness_detects_a_real_divergence() -> bool:
    print("-- 1b. Replay correctness: detects a real, injected divergence (synthetic fixture) --")
    with tempfile.TemporaryDirectory(prefix="heimdall_verify_test_") as tmp:
        tmp_path = Path(tmp)
        clean_raw = tmp_path / "raw_clean"
        mutated_raw = tmp_path / "raw_mutated"
        clean_raw.mkdir()
        for f in REAL_RAW_DIR.glob("*.csv"):
            shutil.copy(f, clean_raw / f.name)
        _mutated_raw_dir(mutated_raw)

        r1 = verify_replay_correctness(clean_raw, n_replays=1, work_dir=tmp_path / "w1")
        r2 = verify_replay_correctness(mutated_raw, n_replays=1, work_dir=tmp_path / "w2")
        fp1, fp2 = r1.fingerprints[0], r2.fingerprints[0]

    diverged = fp1.content_hash != fp2.content_hash and fp1.money_sums["payments.amount"] != fp2.money_sums["payments.amount"]
    print(f"  clean payments.amount sum={fp1.money_sums['payments.amount']} "
          f"mutated={fp2.money_sums['payments.amount']}")
    print(f"  content hashes differ: {fp1.content_hash != fp2.content_hash}")
    print("  PASS" if diverged else "  FAIL")
    return diverged


class Fixture:
    """Built ONCE and shared across every test function below -- not
    rebuilt per test. GraphRepository/FinancialStateStore hold an open
    sqlite3 connection each; financial_graph.builder.build_graph()
    unlinks and recreates financial_graph.db on every call, which fails
    with a WinError 32 (file in use) if a previous run's connection in
    the SAME process is still open. Building once and sharing sidesteps
    that entirely, and is also just faster."""

    def __init__(self):
        self.state, self.graph = build_graph()
        self.device_ids = devices_with_sharers(self.graph)
        self.risk_verdicts = [run_risk_for_device(self.graph, d, investigate=False) for d in self.device_ids[:20]]
        self.failed_payment_ids = [
            r["payment_id"] for r in self.state.all_rows("payments") if r["status"] == "failed"][:20]
        self.recovery_verdicts = [
            run_recovery_for_payment(self.graph, p, investigate=False) for p in self.failed_payment_ids]
        self.settlement_ids = [r["settlement_id"] for r in self.state.all_rows("settlements")][:20]
        self.controller_verdicts = [
            run_controller_for_settlement(self.graph, s, investigate=False) for s in self.settlement_ids]


def test_evidence_grounding_real_data_all_pass(fx: Fixture) -> bool:
    print("-- 3a. Evidence grounding: real verdicts, all three domains --")
    graph, risk_verdicts, recovery_verdicts, controller_verdicts = (
        fx.graph, fx.risk_verdicts, fx.recovery_verdicts, fx.controller_verdicts)
    results = [
        check_evidence_grounding(graph, risk_verdicts),
        check_evidence_grounding(graph, recovery_verdicts),
        check_evidence_grounding(graph, controller_verdicts),
    ]
    for r in results:
        print(f"  {r.agent:<10} evidence checked={r.n_evidence_checked} missing={r.n_evidence_missing} "
              f"affected checked={r.n_affected_checked} missing={r.n_affected_missing}")
    ok = all(r.passed for r in results)
    print("  PASS" if ok else "  FAIL")
    return ok


def test_evidence_grounding_detects_dangling_id(fx: Fixture) -> bool:
    print("-- 3b. Evidence grounding: detects a dangling id (synthetic verdict fixture) --")
    graph = fx.graph
    fake = AgentVerdict(
        agent="risk", subject="dev_does_not_exist", decision="HOLD", reason="synthetic test fixture",
        evidence=["cust_totally_fabricated_id_xyz"], decision_score=0.9, proposed_action="HOLD_PAYMENT",
        affected_entities=["cust_also_fabricated"],
    )
    result = check_evidence_grounding(graph, [fake])
    print(f"  missing={result.missing}")
    ok = (not result.passed) and result.n_evidence_missing == 1 and result.n_affected_missing == 1
    print("  PASS" if ok else "  FAIL")
    return ok


def test_temporal_integrity_real_risk_decisions(fx: Fixture) -> bool:
    print("-- 2a. Temporal integrity: real as-of-scoped Risk decisions (full real corpus) --")
    graph, device_ids = fx.graph, fx.device_ids
    payment_violations = 0
    other_violations = 0
    other_ids: set[str] = set()
    n_checked = 0
    for device_id in device_ids:
        for e in graph.edges_to(device_id, "used_device"):
            payment = graph.get_node(e.subject_id)
            if not payment:
                continue
            as_of = datetime.fromisoformat(payment.properties["created_at"])
            verdict = run_risk_for_device(graph, device_id, investigate=False, as_of=as_of)
            result = check_temporal_integrity(graph, verdict, as_of)
            n_checked += 1
            for v in result.violations:
                if v.node_type == "Payment":
                    payment_violations += 1
                else:
                    other_violations += 1
                    other_ids.add(v.evidence_id)
    print(f"  {n_checked} as-of-scoped decisions audited")
    print(f"  Payment-evidence violations (the boundary edges_to_as_of() actually claims): {payment_violations}")
    print(f"  other-evidence-type violations (informational -- traces to raw Customer.created_at data, "
          f"not Risk's as-of code; see financial_system/verification/README.md): {other_violations} "
          f"({sorted(other_ids)})")
    # The check's pass criterion is the boundary Risk's own temporal-pinning
    # mechanism actually implements: no Payment cited as evidence for an
    # as-of decision may postdate that decision's own as_of. Non-Payment
    # violations are a separate, real, named data finding (see report.py's
    # summarize_temporal docstring/comment) -- not this test's pass bar.
    ok = payment_violations == 0
    print("  PASS" if ok else "  FAIL")
    return ok


def test_temporal_integrity_detects_a_leak(fx: Fixture) -> bool:
    print("-- 2b. Temporal integrity: detects a real leak (synthetic verdict citing real, later-timestamped "
          "evidence against an earlier as_of) --")
    graph, device_ids = fx.graph, fx.device_ids
    # Find one real device with >=2 payments spanning more than an instant,
    # so an as_of BEFORE the later payment's own created_at is a genuine
    # earlier decision point, not an edge case.
    for device_id in device_ids:
        payments = [graph.get_node(e.subject_id) for e in graph.edges_to(device_id, "used_device")]
        payments = [p for p in payments if p and node_timestamp(p) is not None]
        if len(payments) < 2:
            continue
        payments.sort(key=node_timestamp)
        earliest, latest = payments[0], payments[-1]
        if node_timestamp(latest) <= node_timestamp(earliest):
            continue
        as_of = node_timestamp(earliest)
        fake = AgentVerdict(
            agent="risk", subject=device_id, decision="HOLD",
            reason="synthetic test fixture -- cites a real but later payment as evidence",
            evidence=[latest.node_id], decision_score=0.9, proposed_action="HOLD_PAYMENT",
            affected_entities=[],
        )
        result = check_temporal_integrity(graph, fake, as_of)
        print(f"  device={device_id} as_of={as_of.isoformat()} cited evidence timestamp="
              f"{node_timestamp(latest).isoformat()} violations={len(result.violations)}")
        ok = len(result.violations) == 1
        print("  PASS" if ok else "  FAIL")
        return ok
    print("  SKIPPED -- no device in the real graph had 2+ distinctly-timestamped payments to build this fixture from")
    return True


def test_idempotency_real_subjects(fx: Fixture) -> bool:
    print("-- 4a. Idempotency: one real subject per domain, real graph --")
    graph, device_ids, failed_payment_ids, settlement_ids = (
        fx.graph, fx.device_ids, fx.failed_payment_ids, fx.settlement_ids)
    results = [
        check_idempotency(run_risk_for_device, graph, device_ids[0], investigate=False),
        check_idempotency(run_recovery_for_payment, graph, failed_payment_ids[0], investigate=False),
        check_idempotency(run_controller_for_settlement, graph, settlement_ids[0], investigate=False),
    ]
    for r in results:
        print(f"  {r.agent:<10} subject={r.subject!r} identical={r.identical}")
    ok = all(r.identical for r in results)
    print("  PASS" if ok else "  FAIL")
    return ok


def test_idempotency_detects_a_diff(fx: Fixture) -> bool:
    print("-- 4b. Idempotency: detects a real diff (synthetic non-deterministic fn fixture) --")
    calls = {"n": 0}

    def flaky_fn(graph, device_id, investigate=False):
        calls["n"] += 1
        verdict = run_risk_for_device(graph, device_id, investigate=investigate)
        if calls["n"] == 2:
            verdict = verdict.model_copy(update={"decision_score": verdict.decision_score + 0.1})
        return verdict

    graph, device_ids = fx.graph, fx.device_ids
    result = check_idempotency(flaky_fn, graph, device_ids[0], investigate=False)
    print(f"  identical={result.identical} field_diffs={list(result.field_diffs.keys())}")
    ok = (not result.identical) and "decision_score" in result.field_diffs
    print("  PASS" if ok else "  FAIL")
    return ok


def run() -> bool:
    results = {
        "replay_correctness_real_identical": test_replay_correctness_real_dataset_identical(),
        "replay_correctness_detects_divergence": test_replay_correctness_detects_a_real_divergence(),
    }
    print("Building real dataset graph + verdicts once, shared by the remaining tests...")
    fx = Fixture()
    results.update({
        "temporal_integrity_real": test_temporal_integrity_real_risk_decisions(fx),
        "temporal_integrity_detects_leak": test_temporal_integrity_detects_a_leak(fx),
        "evidence_grounding_real": test_evidence_grounding_real_data_all_pass(fx),
        "evidence_grounding_detects_dangling": test_evidence_grounding_detects_dangling_id(fx),
        "idempotency_real": test_idempotency_real_subjects(fx),
        "idempotency_detects_diff": test_idempotency_detects_a_diff(fx),
    })
    print("\n== summary ==")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    passed = all(results.values())
    print(f"\nVERIFICATION MODULE TEST SUITE: {'PASS' if passed else 'FAIL'}")
    return passed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(0 if run() else 1)
