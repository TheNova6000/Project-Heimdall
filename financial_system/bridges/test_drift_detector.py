"""
Tests for drift_detector.py.

Two kinds of tests, matching this task's own explicit requirement:

1. SYNTHETIC, deliberately-constructed cases that contradict a named Truman
   mechanism -- each check function is called directly against a
   hand-built (SimpleNamespace-based, duck-typed) fake report/run/bridge-
   result, so these tests are fast and need no real simulation run. They
   prove the detector actually CAN catch a real drift case, not just that
   it always prints MATCH.

2. REAL, not synthetic: the fast (population=20, days=10) live-recovery-
   loop configuration already established by test_live_recovery_loop.py
   (same file, same params) is run for real, and the checks are run
   against its real output. Matches this project's own convention: fast
   config for the automated suite, the full 90-day demonstration run is a
   separate, manually-verified, one-off (see drift_detector_README.md).
"""
from __future__ import annotations

import datetime
import shutil
from pathlib import Path
from types import SimpleNamespace

from financial_system.bridges.drift_detector import (
    check_decision_score_vs_realized_rate,
    check_device_sharing_vs_risk_scoring,
    check_retry_timing_vs_payday_mechanism,
    run_drift_detector,
)
from financial_system.bridges.live_recovery_loop import LiveLoopReport, RetryOutcome, RetrySchedule
from financial_system.recovery.signals import FAILURE_TAXONOMY

_WORK_ROOT = Path(__file__).resolve().parent / "_test_drift_detector_work"
_FAST_PARAMS = dict(seed=42, population=20, banks=2, merchants=4, days=10,
                     start_date=datetime.date(2026, 1, 1))


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _fake_run(paydays: dict[str, int]) -> SimpleNamespace:
    return SimpleNamespace(persons=[{"person_id": pid, "payday": pd} for pid, pd in paydays.items()])


def _fake_live_report(retries_scheduled=(), retries_attempted=()) -> LiveLoopReport:
    return LiveLoopReport(
        seed=0, population=1, days=1, checkpoints_run=1, total_transactions_final=0,
        failed_payments_total=len(retries_scheduled),
        retries_scheduled=list(retries_scheduled), retries_attempted=list(retries_attempted),
    )


def _fake_risk_verdict(subject: str, n_sharers: int, decision_score: float, decision: str,
                        n_sharers_score: float | None = None) -> SimpleNamespace:
    if n_sharers_score is None:
        n_sharers_score = max(0.0, min(1.0, (n_sharers - 1) / 3))
    return SimpleNamespace(
        subject=subject, decision_score=decision_score, decision=decision,
        metrics={"n_sharers": float(n_sharers), "n_sharers_score": n_sharers_score},
    )


# ---------------------------------------------------------------------------
# Check 1 -- synthetic
# ---------------------------------------------------------------------------


def test_check1_synthetic_drift_structurally_doomed_retry_that_succeeded():
    """A retry scheduled for a day that is NOT the person's payday (so, per
    Truman's own mechanism, balance cannot have grown) but which the
    live-loop report claims succeeded anyway -- exactly the kind of
    contradiction with a known mechanism this detector exists to catch."""
    start = datetime.date(2026, 1, 1)
    sched = RetrySchedule(original_transaction_id="txn_00000001", person_id="person_00001",
                           merchant_id="merch_00000001", amount=100.0, target_day=5,
                           proposed_action="RETRY_LATER", failure_day=4)
    report = _fake_live_report(
        retries_scheduled=[sched],
        retries_attempted=[RetryOutcome(original_transaction_id="txn_00000001", day_attempted=5, succeeded=True)],
    )
    # start + 5 days = 2026-01-06 (day-of-month 6) -- payday=15 means this retry is structurally doomed.
    run = _fake_run({"person_00001": 15})
    result = check_retry_timing_vs_payday_mechanism(report, run, start)
    assert result.verdict == "DRIFT-DETECTED"
    assert "1 succeeded anyway" in result.detail


def test_check1_real_mechanism_case_reports_match():
    """The same shape, but the doomed retry genuinely fails (as Truman's
    mechanism predicts) -- must report MATCH, not drift."""
    start = datetime.date(2026, 1, 1)
    sched = RetrySchedule(original_transaction_id="txn_00000001", person_id="person_00001",
                           merchant_id="merch_00000001", amount=100.0, target_day=5,
                           proposed_action="RETRY_LATER", failure_day=4)
    report = _fake_live_report(
        retries_scheduled=[sched],
        retries_attempted=[RetryOutcome(original_transaction_id="txn_00000001", day_attempted=5, succeeded=False)],
    )
    run = _fake_run({"person_00001": 15})
    result = check_retry_timing_vs_payday_mechanism(report, run, start)
    assert result.verdict == "MATCH"


def test_check1_no_retries_is_inconclusive():
    start = datetime.date(2026, 1, 1)
    report = _fake_live_report()
    run = _fake_run({})
    result = check_retry_timing_vs_payday_mechanism(report, run, start)
    assert result.verdict == "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Check 2 -- synthetic
# ---------------------------------------------------------------------------


def _fake_retries_attempted(n: int, k: int) -> list[RetryOutcome]:
    return [RetryOutcome(original_transaction_id=f"txn_{i:08d}", day_attempted=1, succeeded=(i < k))
            for i in range(n)]


def test_check2_synthetic_drift_all_succeed():
    """decision_score for insufficient_funds is well below 1.0 (confirmed
    below); 10/10 real successes is a known, deliberately-constructed
    contradiction of that stated base rate -- must be caught."""
    decision_score = FAILURE_TAXONOMY["insufficient_funds"]["base_success_rate"]
    assert decision_score < 0.9, "test assumption: the real base rate is well below 1.0"
    report = _fake_live_report(retries_attempted=_fake_retries_attempted(10, 10))
    result = check_decision_score_vs_realized_rate(report)
    assert result.verdict == "DRIFT-DETECTED"


def test_check2_synthetic_match_exact_rate():
    decision_score = FAILURE_TAXONOMY["insufficient_funds"]["base_success_rate"]
    n = 20
    k = round(n * decision_score)
    report = _fake_live_report(retries_attempted=_fake_retries_attempted(n, k))
    result = check_decision_score_vs_realized_rate(report)
    assert result.verdict == "MATCH"


def test_check2_small_sample_is_inconclusive():
    report = _fake_live_report(retries_attempted=_fake_retries_attempted(3, 3))
    result = check_decision_score_vs_realized_rate(report)
    assert result.verdict == "INCONCLUSIVE"


def test_check2_zero_attempts_is_inconclusive():
    report = _fake_live_report()
    result = check_decision_score_vs_realized_rate(report)
    assert result.verdict == "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Check 3 -- synthetic
# ---------------------------------------------------------------------------


def test_check3_synthetic_drift_formula_mismatch():
    """n_sharers_score for n_sharers=2 must be exactly clamp((2-1)/3) =
    0.333... -- a device carrying a wrong value contradicts risk/scoring.py's
    own documented formula and must be caught, regardless of sample size."""
    verdicts = [_fake_risk_verdict("dev_1", n_sharers=2, decision_score=0.5, decision="REVIEW",
                                    n_sharers_score=0.9)]
    result = check_device_sharing_vs_risk_scoring({"risk_verdicts": verdicts})
    assert result.verdict == "DRIFT-DETECTED"


def test_check3_synthetic_drift_negative_correlation():
    """Correct per-device formula, but decision_score falls as n_sharers
    rises across two well-populated buckets -- the opposite of what
    risk/scoring.py's own positive n_sharers weight structurally implies."""
    verdicts = [_fake_risk_verdict(f"low_{i}", n_sharers=2, decision_score=0.9, decision="REVIEW")
                for i in range(6)]
    verdicts += [_fake_risk_verdict(f"high_{i}", n_sharers=4, decision_score=0.1, decision="RELEASE")
                 for i in range(6)]
    result = check_device_sharing_vs_risk_scoring({"risk_verdicts": verdicts})
    assert result.verdict == "DRIFT-DETECTED"


def test_check3_synthetic_match_positive_correlation():
    verdicts = [_fake_risk_verdict(f"low_{i}", n_sharers=2, decision_score=0.1, decision="RELEASE")
                for i in range(6)]
    verdicts += [_fake_risk_verdict(f"high_{i}", n_sharers=4, decision_score=0.9, decision="REVIEW")
                 for i in range(6)]
    result = check_device_sharing_vs_risk_scoring({"risk_verdicts": verdicts})
    assert result.verdict == "MATCH"


def test_check3_small_buckets_inconclusive():
    verdicts = [_fake_risk_verdict("dev_1", n_sharers=2, decision_score=0.3, decision="RELEASE"),
                _fake_risk_verdict("dev_2", n_sharers=3, decision_score=0.5, decision="REVIEW")]
    result = check_device_sharing_vs_risk_scoring({"risk_verdicts": verdicts})
    assert result.verdict == "INCONCLUSIVE"


def test_check3_no_shared_devices_inconclusive():
    result = check_device_sharing_vs_risk_scoring({"risk_verdicts": []})
    assert result.verdict == "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Real, not synthetic: the fast live-loop configuration, for real
# ---------------------------------------------------------------------------


def _run(work_subdir: str):
    work_dir = _WORK_ROOT / work_subdir
    if work_dir.exists():
        shutil.rmtree(work_dir)
    return run_drift_detector(**_FAST_PARAMS, live_work_dir=work_dir)


def test_real_fast_run_check1_reports_match():
    """At seed=42/population=20/days=10, real Recovery decisions and real
    retry outcomes are produced by an actual live-recovery-loop run (no
    fixture, no mock). Check 1 must report MATCH -- no structurally-doomed
    retry has ever been observed to succeed in this project's own real,
    already-documented runs (Simulation/docs/Memory.md: 0/22 succeeded in
    the 90-day demonstration run; this fast 10-day run reproduces the same
    mechanism at smaller scale)."""
    result = _run("real_check1")
    check1 = next(c for c in result.checks if c.check_id == "1")
    assert result.live_report.checkpoints_run == 10
    assert len(result.live_report.retries_scheduled) >= 1, "expected at least one real RETRY in this deterministic run"
    assert check1.verdict == "MATCH"


def test_real_fast_run_check2_reports_real_verdict_honestly():
    """At this small scale only 1 retry is actually attempted within the
    10-day window (n < 5), so Check 2 must honestly report INCONCLUSIVE --
    not a forced MATCH or DRIFT. (The full 90-day run has n=22 and DOES
    reach statistical significance -- see drift_detector_README.md's real
    numbers; this fast test intentionally uses the small-n case to prove
    the detector does NOT overclaim from too little data.)"""
    result = _run("real_check2")
    check2 = next(c for c in result.checks if c.check_id == "2")
    n_attempted = len(result.live_report.retries_attempted)
    if n_attempted < 5:
        assert check2.verdict == "INCONCLUSIVE"
    else:
        assert check2.verdict in ("MATCH", "DRIFT-DETECTED")


def test_real_run_is_deterministic():
    """Same seed/config -> identical check verdicts and detail text across
    two independent runs -- same determinism discipline as every other
    module in this project (Simulation/docs/Rules.md #6)."""
    r1 = _run("det_a")
    r2 = _run("det_b")
    assert [(c.check_id, c.verdict, c.detail) for c in r1.checks] == \
           [(c.check_id, c.verdict, c.detail) for c in r2.checks]


def teardown_module(module):
    if _WORK_ROOT.exists():
        shutil.rmtree(_WORK_ROOT, ignore_errors=True)
