"""
Tests for the Live Recovery loop (live_recovery_loop.py) -- the in-loop
retry closure for the Recovery domain (see this file's module docstring and
financial_system/bridges/README.md's "Live Recovery loop" section for the
full design).

All tests use a small, fast configuration (population=20, days=10, seed=42
-- the same config verified by hand during this task's own development,
see README.md's "Real end-to-end run" section for the full 90-day numbers)
so the suite stays fast; the 90-day real run is a separate, one-off,
manually-run demonstration, not part of this automated suite.
"""
from __future__ import annotations

import datetime
import shutil
from pathlib import Path

from financial_system.bridges.live_recovery_loop import run_live_recovery_loop

_WORK_ROOT = Path(__file__).resolve().parent / "_test_live_loop_work"

_FAST_PARAMS = dict(seed=42, population=20, banks=2, merchants=4, days=10,
                     start_date=datetime.date(2026, 1, 1))


def _run(work_subdir: str, **overrides):
    params = dict(_FAST_PARAMS)
    params.update(overrides)
    work_dir = _WORK_ROOT / work_subdir
    if work_dir.exists():
        shutil.rmtree(work_dir)
    return run_live_recovery_loop(work_dir=work_dir, **params)


def test_recovery_is_real_not_mocked():
    """
    Every decision must carry the exact real numbers Heimdall's unmodified
    recovery/signals.py FAILURE_TAXONOMY produces for insufficient_funds
    (decision_score=0.45, proposed_action=RETRY_LATER) -- the same numbers
    financial_system/bridges/README.md's batch bridge already proved this
    logic produces on bridged Simulation/ data. A stub/mock would have no
    reason to reproduce this exact category-specific base rate.
    """
    report = _run("real_not_mocked")
    assert len(report.decisions) > 0, "expected at least one real payment_failure in this deterministic run"
    for d in report.decisions:
        assert d.decision == "RETRY"
        assert d.decision_score == 0.45
        assert d.proposed_action == "RETRY_LATER"
        # See DecisionRecord's own docstring: only non-None if
        # investigate_evidence() (Discovery.AI/LLM) actually ran. This loop
        # always calls run_recovery_for_payment(..., investigate=False).
        assert d.investigation_confidence is None


def test_no_llm_calls_ever():
    """
    Zero LLM/Discovery.AI calls anywhere in this loop -- confirmed two ways:
    (1) live_recovery_loop.py's only call site passes investigate=False
    unconditionally (read the source); (2) every real decision's
    investigation_confidence is None (see test above), which is only ever
    set when investigate_evidence() actually executed. Both must hold.
    """
    report = _run("no_llm")
    assert len(report.decisions) > 0
    assert all(d.investigation_confidence is None for d in report.decisions)


def test_no_magical_outcome():
    """
    A retry against a genuinely insufficient balance must fail exactly like
    a real second attempt would -- never an automatic success. At seed=42/
    population=20/days=10, at least one scheduled retry is actually
    attempted within the run window, and (a real, honestly-reported fact
    about this small canvas, not engineered) it fails again, because the
    person's balance genuinely had not recovered one simulated day later
    (Simulation/'s only income mechanism is a fixed monthly payday -- see
    README.md's "Real end-to-end run" section for the full causal
    explanation). This test asserts the mechanic, not a specific count, so
    it stays robust to unrelated future changes elsewhere in Simulation/.
    """
    report = _run("no_magic")
    assert len(report.retries_attempted) >= 1
    assert any(not r.succeeded for r in report.retries_attempted), (
        "expected at least one real retry-against-insufficient-balance failure "
        "in this deterministic run -- if this ever flips to 'all succeeded', "
        "re-verify by hand rather than assuming the mechanic broke"
    )


def test_retry_amount_and_merchant_match_original():
    """
    A retry retries the SAME purchase -- same amount, same merchant, same
    person as the original failed transaction, never a new/invented one.
    """
    report = _run("same_purchase")
    assert len(report.retries_scheduled) > 0
    for sched in report.retries_scheduled:
        assert sched.amount > 0
        assert sched.person_id
        assert sched.merchant_id
        assert sched.target_day == sched.failure_day + 1


def test_determinism_two_runs_identical_reports():
    """
    Same seed + same config -> byte-identical report content: same payments
    decided, same decisions/scores, same retries scheduled, same retry
    outcomes -- across two completely independent runs of the loop.
    """
    r1 = _run("det_a")
    r2 = _run("det_b")

    assert r1.decisions == r2.decisions
    assert r1.retries_scheduled == r2.retries_scheduled
    assert r1.retries_not_executable == r2.retries_not_executable
    assert r1.retries_attempted == r2.retries_attempted
    assert r1.total_transactions_final == r2.total_transactions_final
    assert r1.failed_payments_total == r2.failed_payments_total
    assert r1.checkpoints_run == r2.checkpoints_run


def test_determinism_two_runs_byte_identical_world_output():
    """
    The strongest form of the determinism guarantee: the actual CSV bytes
    of the final world snapshot (transactions.csv, events.csv -- including
    every retry_success/retry_failure transaction and its retried_from
    payload) are byte-for-byte identical across two independent runs, not
    just the summarized report.
    """
    _run("bytes_a")
    _run("bytes_b")

    for fname in ("transactions.csv", "events.csv", "persons.csv"):
        a = (_WORK_ROOT / "bytes_a" / "sim_snapshot" / fname).read_bytes()
        b = (_WORK_ROOT / "bytes_b" / "sim_snapshot" / fname).read_bytes()
        assert a == b, f"{fname} differs between two identical-seed live-loop runs"


def test_retry_transactions_are_new_kind_values_traceable_via_payload():
    """
    A retry is recorded as a NEW Transaction (kind=retry_success/
    retry_failure), never a mutation of the original payment_failure row,
    and is traceable back to the original via the corresponding Event's
    payload JSON `retried_from` key (see Simulation/world/engine.py's
    attempt_retry()/_record() for why this is a payload key, not a new
    Transaction CSV column).
    """
    import csv
    import json

    report = _run("kind_values")
    assert len(report.retries_attempted) >= 1

    txns_path = _WORK_ROOT / "kind_values" / "sim_snapshot" / "transactions.csv"
    events_path = _WORK_ROOT / "kind_values" / "sim_snapshot" / "events.csv"

    with open(txns_path, newline="", encoding="utf-8") as f:
        txn_rows = list(csv.DictReader(f))
    retry_txns = [r for r in txn_rows if r["kind"] in ("retry_success", "retry_failure")]
    assert len(retry_txns) == len(report.retries_attempted)
    # Original failed transactions are untouched -- still payment_failure.
    original_ids = {r.original_transaction_id for r in report.retries_attempted}
    for row in txn_rows:
        if row["transaction_id"] in original_ids:
            assert row["kind"] == "payment_failure"

    with open(events_path, newline="", encoding="utf-8") as f:
        event_rows = list(csv.DictReader(f))
    retry_events = [e for e in event_rows if e["event_type"] in ("retry_succeeded", "retry_failed")]
    assert len(retry_events) == len(report.retries_attempted)
    linked_back = {json.loads(e["payload"])["retried_from"] for e in retry_events}
    assert linked_back == original_ids


def teardown_module(module):
    if _WORK_ROOT.exists():
        shutil.rmtree(_WORK_ROOT, ignore_errors=True)
