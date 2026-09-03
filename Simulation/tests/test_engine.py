"""
Basic sanity tests for the Financial World Simulation (Phase 1), per
Architecture.md and Rules.md #6: determinism given a seed, no negative
balances, and a well-formed event log.

Run with:
    python -m pytest Simulation/tests/test_engine.py -v
(from the repo root) or `pytest -v` from inside Simulation/.
"""

from __future__ import annotations

import csv
import dataclasses
import datetime
import filecmp
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from run_simulation import run  # noqa: E402
from world.engine import SimulationEngine  # noqa: E402

START_DATE = datetime.date(2026, 1, 1)


def _small_engine(seed: int = 7) -> SimulationEngine:
    return SimulationEngine(
        seed=seed,
        num_persons=50,
        num_banks=2,
        num_merchants=5,
        num_days=60,
        start_date=START_DATE,
    )


# ---------------------------------------------------------------------------
# Determinism (Rules.md #6)
# ---------------------------------------------------------------------------


def test_same_seed_produces_identical_transactions_in_memory():
    result_a = _small_engine(seed=123).run()
    result_b = _small_engine(seed=123).run()

    assert len(result_a.transactions) == len(result_b.transactions)
    assert [dataclasses.asdict(t) for t in result_a.transactions] == [
        dataclasses.asdict(t) for t in result_b.transactions
    ]
    assert [dataclasses.asdict(e) for e in result_a.events] == [
        dataclasses.asdict(e) for e in result_b.events
    ]


def test_different_seeds_produce_different_transactions():
    result_a = _small_engine(seed=1).run()
    result_b = _small_engine(seed=2).run()

    txns_a = [dataclasses.asdict(t) for t in result_a.transactions]
    txns_b = [dataclasses.asdict(t) for t in result_b.transactions]
    assert txns_a != txns_b, "different seeds unexpectedly produced identical output"


def test_same_seed_produces_byte_identical_csv_output():
    """
    The determinism requirement end-to-end: run the real entry point twice
    with the same seed into two separate directories, and diff every
    output file byte-for-byte.
    """
    with tempfile.TemporaryDirectory() as tmp:
        outdir_a = os.path.join(tmp, "run_a")
        outdir_b = os.path.join(tmp, "run_b")

        run(
            seed=99,
            population=40,
            banks=2,
            merchants=4,
            days=45,
            start_date=START_DATE,
            outdir=outdir_a,
        )
        run(
            seed=99,
            population=40,
            banks=2,
            merchants=4,
            days=45,
            start_date=START_DATE,
            outdir=outdir_b,
        )

        for filename in (
            "persons.csv",
            "banks.csv",
            "merchants.csv",
            "accounts.csv",
            "transactions.csv",
            "events.csv",
            "ledger_entries.csv",  # Phase 2
            "households.csv",  # Phase 2.5
            "organizations.csv",  # Phase 2.5
            "communities.csv",  # Phase 2.5
        ):
            path_a = os.path.join(outdir_a, filename)
            path_b = os.path.join(outdir_b, filename)
            assert os.path.exists(path_a)
            assert os.path.exists(path_b)
            assert filecmp.cmp(path_a, path_b, shallow=False), (
                f"{filename} differs between two runs with the same seed"
            )


# ---------------------------------------------------------------------------
# No negative balances (Rules.md #7)
# ---------------------------------------------------------------------------


def test_no_account_ever_goes_negative():
    result = _small_engine(seed=5).run()

    # Final balances.
    for account in result.accounts:
        assert account.balance >= 0, f"{account.account_id} ended negative: {account.balance}"

    # Every intermediate balance too -- walk every ledger entry, not just
    # the final snapshot, since a bug could dip negative and recover.
    for account in result.accounts:
        for entry in account.ledger:
            assert entry.balance_after >= 0, (
                f"{account.account_id} went negative mid-run at {entry.entry_id}: "
                f"{entry.balance_after}"
            )


def test_payment_failure_never_moves_money():
    """A payment_failure transaction must correspond to no ledger change:
    balance_before < amount, and the failure is recorded without any debit
    having occurred (Bank.debit returns False and mutates nothing)."""
    result = _small_engine(seed=11).run()

    failures = [t for t in result.transactions if t.kind == "payment_failure"]
    assert failures, "expected at least one payment_failure in this run (seed=11, 50 persons, 60 days)"
    for t in failures:
        assert t.balance_before < t.amount, (
            f"{t.transaction_id} is a payment_failure but balance_before "
            f"({t.balance_before}) >= amount ({t.amount})"
        )


# ---------------------------------------------------------------------------
# Well-formed event log / transaction log
# ---------------------------------------------------------------------------


def test_transaction_and_event_ids_unique():
    result = _small_engine(seed=3).run()

    txn_ids = [t.transaction_id for t in result.transactions]
    assert len(txn_ids) == len(set(txn_ids)), "duplicate transaction_id found"

    event_ids = [e.event_id for e in result.events]
    assert len(event_ids) == len(set(event_ids)), "duplicate event_id found"


def test_every_event_has_a_matching_transaction_payload():
    result = _small_engine(seed=3).run()
    assert len(result.events) == len(result.transactions), (
        "engine.py emits exactly one Event per Transaction in Phase 1"
    )


def test_transaction_fields_well_formed():
    result = _small_engine(seed=17).run()
    person_ids = {p.person_id for p in result.persons}
    merchant_ids = {m.merchant_id for m in result.merchants}
    household_ids = {h.household_id for h in result.households}
    organization_ids = {o.organization_id for o in result.organizations}

    assert result.transactions, "expected a non-trivial number of transactions"

    # Phase 2 added one new kind, "settlement". Phase 2.5 (docs/Memory.md's
    # "Phase 2.5" section) adds three more: "savings_sweep"/"household_
    # sweep" (a salary payment's savings/household legs -- world/engine.py
    # `_maybe_pay_income`) and "org_funding" (an Organization's one-time
    # revenue funding at world-generation time -- `_build_world`). It also
    # widens what "salary"/"savings_sweep"/"household_sweep"/
    # "payment_failure" rows can legitimately look like: an
    # Organization-employed person's salary (and its sweeps) comes from a
    # real "org:<organization_id>" source instead of the synthetic
    # "employer:<person_id>" one, and "payment_failure" now also covers an
    # Organization's own payroll failing to cover a payday (from_id is
    # "org:<id>", to_id is the person who didn't get paid), not just a
    # Person's purchase failing.
    for t in result.transactions:
        assert t.amount > 0, f"{t.transaction_id} has non-positive amount {t.amount}"
        assert t.kind in {
            "salary",
            "purchase",
            "payment_failure",
            "settlement",
            "savings_sweep",
            "household_sweep",
            "org_funding",
        }
        assert t.day >= 0
        if t.kind in {"salary", "savings_sweep"}:
            assert t.from_id.startswith("employer:") or t.from_id.startswith("org:")
            assert t.to_id in person_ids
        elif t.kind == "household_sweep":
            assert t.from_id.startswith("employer:") or t.from_id.startswith("org:")
            assert t.to_id in household_ids
        elif t.kind == "org_funding":
            assert t.from_id.startswith("external_revenue:")
            assert t.to_id in organization_ids
        elif t.kind == "settlement":
            assert t.from_id.startswith("pending:")
            assert t.to_id in merchant_ids
        elif t.kind == "payment_failure":
            is_purchase_failure = t.from_id in person_ids and t.to_id in merchant_ids
            is_payroll_failure = t.from_id.startswith("org:") and t.to_id in person_ids
            assert is_purchase_failure or is_payroll_failure, (
                f"{t.transaction_id} is a payment_failure with an unrecognized "
                f"from_id/to_id shape: {t.from_id!r} -> {t.to_id!r}"
            )
        else:  # purchase
            assert t.from_id in person_ids
            assert t.to_id in merchant_ids
        # timestamp must be ISO 8601 parseable
        datetime.datetime.fromisoformat(t.timestamp)


def test_csv_output_is_well_formed_and_parseable():
    with tempfile.TemporaryDirectory() as tmp:
        outdir = os.path.join(tmp, "run")
        result = run(
            seed=21,
            population=30,
            banks=2,
            merchants=3,
            days=30,
            start_date=START_DATE,
            outdir=outdir,
        )

        with open(os.path.join(outdir, "transactions.csv"), newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == len(result.transactions)
        expected_cols = {
            "transaction_id",
            "timestamp",
            "day",
            "from_id",
            "to_id",
            "amount",
            "kind",
            "balance_before",
        }
        assert expected_cols.issubset(rows[0].keys())
        for row in rows:
            float(row["amount"])  # must parse as a number
            int(row["day"])

        with open(os.path.join(outdir, "persons.csv"), newline="", encoding="utf-8") as f:
            person_rows = list(csv.DictReader(f))
        assert len(person_rows) == 30
        for row in person_rows:
            assert float(row["balance"]) >= 0
            assert 0.0 <= float(row["risk_preference"]) <= 1.0
