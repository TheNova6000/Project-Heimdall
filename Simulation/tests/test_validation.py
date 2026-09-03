"""
Tests for the validation system itself (this task's "Part B"), same rigor
standard as the rest of this project (Rules.md #6/#7): feed it a real,
small, deterministic run and check it correctly flags a known PASS (the
internal mechanism checks, which should always hold by construction) and
a known GAP (the spend/income-ratio-vs-income-level check, which
docs/Research.md already documented this simulation's purchase_amount()
mechanism does NOT reproduce).

Run with:
    python -m pytest tests/ -v          (from inside Simulation/)
    python -m pytest tests/test_validation.py -v
"""

from __future__ import annotations

import datetime
import os
import tempfile

from run_simulation import run
from validation.report import (
    build_b1,
    build_b2,
    check_credit_not_applicable,
    check_fraud_not_applicable,
    check_loans_not_applicable,
    check_settlement_timing,
    check_spend_income_ratio_by_income,
)
from validation.sample import RunData, sample_person_ids

START_DATE = datetime.date(2026, 1, 1)


def _run_and_load(seed: int, population: int, days: int, tmp: str) -> RunData:
    outdir = os.path.join(tmp, f"run_{seed}")
    run(
        seed=seed,
        population=population,
        banks=2,
        merchants=4,
        days=days,
        start_date=START_DATE,
        outdir=outdir,
    )
    return RunData(outdir)


def test_b1_checks_all_pass_on_a_real_run():
    """Every B.1 check is an internal-consistency claim that should hold
    by construction on ANY run, not just a cherry-picked one -- this is
    the "known PASS" case."""
    with tempfile.TemporaryDirectory() as tmp:
        run_data = _run_and_load(seed=101, population=150, days=60, tmp=tmp)
        sample_ids = sample_person_ids(run_data, sample_size=None, seed=1)
        results = build_b1(run_data, sample_ids)

    for r in results:
        assert r.verdict == "PASS", f"{r.name} unexpectedly {r.verdict}: {r.detail}"


def test_b2_spend_income_ratio_check_flags_the_known_gap():
    """The documented, expected GAP (docs/Research.md Part A §1 / this
    task's brief): purchase_amount() draws the same fractional range of a
    buyer's own income regardless of income level, so this simulation
    should NOT reproduce the real-world declining spend/income-ratio-by-
    income pattern. This is checked against a real run's actual output,
    not asserted from prose."""
    with tempfile.TemporaryDirectory() as tmp:
        run_data = _run_and_load(seed=202, population=300, days=90, tmp=tmp)
        sample_ids = sample_person_ids(run_data, sample_size=None, seed=1)
        result = check_spend_income_ratio_by_income(run_data, sample_ids)

    assert result.verdict == "GAP", (
        f"expected the documented spend/income-ratio gap to be flagged as GAP, got "
        f"{result.verdict}: {result.detail}"
    )


def test_b2_settlement_timing_check_passes():
    """T+1 settlement is always exactly one simulated day (tests/
    test_ledger.py already proves this mechanically); this is the known
    PASS case for a B.2 check specifically."""
    with tempfile.TemporaryDirectory() as tmp:
        run_data = _run_and_load(seed=303, population=100, days=45, tmp=tmp)
        result = check_settlement_timing(run_data)

    assert result.verdict == "PASS"


def test_b2_unimplemented_mechanisms_report_not_applicable():
    """Fraud/credit/loans must be reported NOT APPLICABLE, never silently
    omitted or fabricated (this task's explicit instruction)."""
    for check_fn in (check_fraud_not_applicable, check_credit_not_applicable, check_loans_not_applicable):
        result = check_fn()
        assert result.verdict == "NOT APPLICABLE"
        assert "not implemented" in result.detail


def test_b2_results_cover_every_researched_and_unimplemented_topic():
    """Sanity check on report completeness: build_b2 must return exactly
    one result per Research.md Part A topic that maps onto something
    implemented (income shape, spend/income ratio, settlement timing) plus
    one NOT APPLICABLE per Part C proposal (fraud, credit, loans) -- 6
    results total, no topic silently dropped."""
    with tempfile.TemporaryDirectory() as tmp:
        run_data = _run_and_load(seed=404, population=80, days=30, tmp=tmp)
        sample_ids = sample_person_ids(run_data, sample_size=None, seed=1)
        results = build_b2(run_data, sample_ids)

    assert len(results) == 6
    not_applicable = [r for r in results if r.verdict == "NOT APPLICABLE"]
    assert len(not_applicable) == 3


def test_sampling_is_deterministic_given_a_seed():
    with tempfile.TemporaryDirectory() as tmp:
        run_data = _run_and_load(seed=505, population=200, days=30, tmp=tmp)
        sample_a = sample_person_ids(run_data, sample_size=50, seed=999)
        sample_b = sample_person_ids(run_data, sample_size=50, seed=999)
        sample_c = sample_person_ids(run_data, sample_size=50, seed=1)

    assert sample_a == sample_b, "same seed must produce the same sample"
    assert len(sample_a) == 50
    assert sample_a != sample_c, "different seeds unexpectedly produced the identical sample"


def test_sample_size_none_uses_full_population():
    with tempfile.TemporaryDirectory() as tmp:
        run_data = _run_and_load(seed=606, population=40, days=20, tmp=tmp)
        sample_ids = sample_person_ids(run_data, sample_size=None, seed=1)

    assert sample_ids == set(run_data.person_ids)
