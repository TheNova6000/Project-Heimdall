"""
Phase 2 tests: the double-entry ledger and merchant settlement.

Mirrors tests/test_engine.py's style and rigor (Rules.md #6/#7): every
new correctness claim Phase 2 makes -- the double-entry invariant, no
negative balances anywhere in the new ledger (including the new account
types), settlement actually delaying availability by one day, and
determinism extending to the new ledger/settlement output -- is checked
here explicitly, not just asserted in prose.

Run with:
    python -m pytest tests/ -v          (from inside Simulation/)
    python -m pytest tests/test_ledger.py -v
"""

from __future__ import annotations

import datetime

from world.engine import SimulationEngine

START_DATE = datetime.date(2026, 1, 1)


def _engine(seed: int = 7, **overrides) -> SimulationEngine:
    kwargs = dict(
        seed=seed,
        num_persons=80,
        num_banks=3,
        num_merchants=6,
        num_days=45,
        start_date=START_DATE,
    )
    kwargs.update(overrides)
    return SimulationEngine(**kwargs)


# ---------------------------------------------------------------------------
# The double-entry invariant -- Phase 2's core new correctness claim
# ---------------------------------------------------------------------------


def test_double_entry_invariant_holds_globally():
    """Sum of every debit-entry amount across every account in every bank
    must exactly equal the sum of every credit-entry amount, at the end
    of a run -- the defining property of a double-entry ledger."""
    result = _engine(seed=42).run()

    debit_total = 0.0
    credit_total = 0.0
    entry_count = 0
    for account in result.accounts:
        for entry in account.ledger:
            entry_count += 1
            assert entry.entry_type in ("debit", "credit"), (
                f"{entry.entry_id} has unexpected entry_type {entry.entry_type!r}"
            )
            if entry.entry_type == "debit":
                debit_total += entry.amount
            else:
                credit_total += entry.amount

    assert entry_count > 0, "expected a non-trivial number of ledger entries"
    assert round(debit_total, 2) == round(credit_total, 2), (
        f"double-entry invariant violated: debits={debit_total} != credits={credit_total}"
    )


def test_double_entry_invariant_holds_per_transaction():
    """A stronger, more localized version of the same check: for every
    individual transaction_id, its own debit entries and credit entries
    must balance -- not just in aggregate across the whole run (which
    could hide an offsetting pair of unrelated imbalances)."""
    result = _engine(seed=11).run()

    by_txn: dict[str, list[float]] = {}
    for account in result.accounts:
        for entry in account.ledger:
            pair = by_txn.setdefault(entry.transaction_id, [0.0, 0.0])
            pair[0 if entry.entry_type == "debit" else 1] += entry.amount

    assert by_txn, "expected at least one ledger-backed transaction"
    for txn_id, (debit, credit) in by_txn.items():
        assert round(debit, 2) == round(credit, 2), (
            f"transaction {txn_id} does not balance: debit={debit} credit={credit}"
        )
        # Every ledger-backed transaction is a simple one-to-one transfer
        # in Phase 2's scope (salary, purchase, settlement) -- exactly
        # two entries (one debit, one credit), never more, never fewer.
        matching_entries = sum(
            1
            for account in result.accounts
            for entry in account.ledger
            if entry.transaction_id == txn_id
        )
        assert matching_entries == 2, (
            f"transaction {txn_id} has {matching_entries} ledger entries, expected exactly 2"
        )


def test_every_ledger_entry_traces_to_a_real_transaction():
    """Every LedgerEntry's transaction_id must correspond to a Transaction
    actually in the output (or the payment_failure case, which posts NO
    ledger entries at all -- checked separately below) -- no orphaned
    ledger postings."""
    result = _engine(seed=3).run()
    txn_ids = {t.transaction_id for t in result.transactions}
    for account in result.accounts:
        for entry in account.ledger:
            assert entry.transaction_id in txn_ids, (
                f"{entry.entry_id} references unknown transaction_id {entry.transaction_id}"
            )


def test_payment_failure_posts_no_ledger_entries():
    """A payment_failure must correspond to zero ledger entries anywhere
    -- Rules.md #7's enforcement point (world/agents/bank.py's
    `post_transfer`) makes no change at all when the source account
    can't cover the amount."""
    result = _engine(seed=11).run()
    failures = [t for t in result.transactions if t.kind == "payment_failure"]
    assert failures, "expected at least one payment_failure in this run"

    failure_ids = {t.transaction_id for t in failures}
    for account in result.accounts:
        for entry in account.ledger:
            assert entry.transaction_id not in failure_ids, (
                f"{entry.entry_id} is linked to payment_failure {entry.transaction_id}, "
                "but a failed payment must move no money at all"
            )


# ---------------------------------------------------------------------------
# No negative balances anywhere in the new ledger (Rules.md #7)
# ---------------------------------------------------------------------------


def test_no_negative_balance_across_all_account_types():
    """Extends tests/test_engine.py's equivalent check to the account
    types Phase 2 introduces (bank_reserve, merchant_pending) AND the
    three Phase 2.5 introduces (person_savings, household,
    organization_revenue -- docs/Memory.md's "Phase 2.5" section). Checked
    at every single ledger entry, not just final state."""
    result = _engine(seed=5).run()

    owner_types_seen = set()
    for account in result.accounts:
        owner_types_seen.add(account.owner_type)
        assert account.balance >= 0, f"{account.account_id} ({account.owner_type}) ended negative"
        for entry in account.ledger:
            assert entry.balance_after >= 0, (
                f"{account.account_id} ({account.owner_type}) went negative at "
                f"{entry.entry_id}: {entry.balance_after}"
            )

    # Sanity: this run actually exercised every account type this
    # simulation currently has, so the check above isn't vacuously true
    # for any of them (Phase 2.5's three new types included).
    assert owner_types_seen == {
        "person",
        "merchant",
        "merchant_pending",
        "bank_reserve",
        "person_savings",
        "household",
        "organization_revenue",
    }


def test_bank_reserve_account_never_decreases():
    """The reserve/asset account is only ever debited (increased) by
    fund_external() in Phase 2's scope -- nothing draws it down. It
    should be monotonically non-decreasing across its own ledger, which
    is *why* it can never go negative (not because of a special-cased
    balance check)."""
    result = _engine(seed=9).run()

    reserve_accounts = [a for a in result.accounts if a.owner_type == "bank_reserve"]
    assert reserve_accounts, "expected at least one bank_reserve account"
    for account in reserve_accounts:
        running = 0.0
        for entry in account.ledger:
            assert entry.entry_type == "debit", (
                f"{account.account_id} received an unexpected {entry.entry_type} entry"
            )
            assert entry.balance_after >= running - 1e-9
            running = entry.balance_after


def test_reserve_account_balance_equals_total_external_inflows():
    """A direct reconciliation: the grand total of every bank's reserve
    account balance should equal the sum of every Transaction that is
    genuinely sourced from `fund_external` (Phase 2's only source of
    external inflow) -- proof the ledger, not just the cached balance
    field, is internally consistent.

    Phase 2.5 note (docs/Memory.md's "Phase 2.5" section): this is a
    NECESSARY, not cosmetic, update to what was
    `test_reserve_account_balance_equals_total_salary_paid` in Phase 2.
    Reserve-account debits are no longer produced by "salary" Transactions
    alone: (a) a synthetic-employer-sourced payday now also sweeps
    "savings_sweep"/"household_sweep" legs through `fund_external`, each
    its own reserve debit, and (b) an Organization-employed person's
    salary/savings_sweep/household_sweep legs do NOT touch any bank's
    reserve account at all -- they move through `post_transfer` from that
    Organization's own revenue account instead (see world/engine.py's
    `_maybe_pay_income`). What DOES still debit a bank_reserve account:
    every synthetic-employer-sourced salary/savings_sweep/household_sweep
    leg (from_id starts with "employer:"), plus each Organization's
    one-time `org_funding` revenue injection (which itself IS `fund_
    external`-sourced, per world/models.py's Organization docstring).
    """
    result = _engine(seed=13).run()

    employer_sourced_kinds = {"salary", "savings_sweep", "household_sweep"}
    total_employer_sourced = sum(
        t.amount
        for t in result.transactions
        if t.kind in employer_sourced_kinds and t.from_id.startswith("employer:")
    )
    total_org_funding = sum(t.amount for t in result.transactions if t.kind == "org_funding")
    total_external_inflow = total_employer_sourced + total_org_funding

    total_reserve = sum(
        entry.amount
        for account in result.accounts
        if account.owner_type == "bank_reserve"
        for entry in account.ledger
    )
    assert round(total_external_inflow, 2) == round(total_reserve, 2)


# ---------------------------------------------------------------------------
# Settlement: received vs. settled are genuinely distinct states
# ---------------------------------------------------------------------------


def test_settlement_transactions_appear():
    result = _engine(seed=42).run()
    settlements = [t for t in result.transactions if t.kind == "settlement"]
    assert settlements, "expected at least one settlement transaction"
    for t in settlements:
        assert t.from_id.startswith("pending:")
        assert t.amount > 0


def test_settlement_events_appear_in_event_log():
    result = _engine(seed=42).run()
    settlement_events = [e for e in result.events if e.event_type == "settlement_completed"]
    assert settlement_events, "expected at least one settlement_completed event"


def test_purchase_proceeds_are_not_immediately_spendable():
    """The specific Phase 2 mechanism: a successful purchase must credit
    the merchant's PENDING account, not their settled/spendable one, on
    the same day. Verified with a small, fully hand-traceable scenario:
    1 person, 1 bank, 1 merchant, so there is no ambiguity about which
    account a purchase's proceeds land in."""
    result = _engine(seed=42, num_persons=1, num_banks=1, num_merchants=1, num_days=10).run()

    purchases = [t for t in result.transactions if t.kind == "purchase"]
    assert purchases, "expected at least one purchase in this scenario"
    first_purchase = purchases[0]
    purchase_day = first_purchase.day

    merchant = result.merchants[0]
    settled_account = next(a for a in result.accounts if a.account_id == merchant.bank_account_id)
    pending_account = next(a for a in result.accounts if a.account_id == merchant.pending_account_id)

    # Immediately after the purchase's own ledger postings on its own
    # day, the merchant's SETTLED account must show no entry from that
    # transaction_id -- only the pending account does.
    settled_entry_txn_ids = {e.transaction_id for e in settled_account.ledger}
    pending_entry_txn_ids = {e.transaction_id for e in pending_account.ledger}
    assert first_purchase.transaction_id in pending_entry_txn_ids
    assert first_purchase.transaction_id not in settled_entry_txn_ids

    # And a settlement transaction for this merchant must occur on a
    # LATER day than the purchase (T+1, never same-day).
    settlements = [
        t
        for t in result.transactions
        if t.kind == "settlement" and t.to_id == merchant.merchant_id
    ]
    assert settlements, "expected the pending proceeds to eventually be settled"
    first_settlement = min(settlements, key=lambda t: t.day)
    assert first_settlement.day > purchase_day, (
        f"settlement on day {first_settlement.day} did not come strictly after "
        f"the purchase on day {purchase_day}"
    )


def test_settlement_is_exactly_next_day():
    """Stronger than 'eventually settled': with only one merchant and one
    bank, every settlement's day must be exactly one simulated day after
    the purchase(s) whose proceeds it moves -- proves T+1, not just
    'some later day' (see world/engine.py `_run_settlement` docstring
    for this rule's provenance)."""
    result = _engine(seed=17, num_persons=25, num_banks=1, num_merchants=1, num_days=20).run()

    purchase_days = {t.day for t in result.transactions if t.kind == "purchase"}
    settlement_days = {t.day for t in result.transactions if t.kind == "settlement"}
    assert purchase_days and settlement_days

    for s_day in settlement_days:
        # Each settlement day must be exactly one day after SOME day that
        # had purchases (the pending balance it swept came from exactly
        # one prior day, by construction -- a full sweep every day).
        assert (s_day - 1) in purchase_days, (
            f"settlement on day {s_day} has no matching purchase day {s_day - 1}"
        )


def test_final_day_purchases_remain_unsettled_at_run_end():
    """Honest, documented edge case (see world/engine.py `_run_settlement`
    docstring and Memory.md): proceeds from the LAST simulated day of a
    run are never swept, since there is no day num_days tick to sweep
    them on. This test proves that's real, deliberate behavior, not an
    accidental gap -- if a future change accidentally added an end-of-run
    settlement sweep, this test would need a matching, intentional
    update, not silently start failing."""
    result = _engine(seed=42, num_persons=60, num_banks=2, num_merchants=4, num_days=15).run()

    last_day = result.num_days - 1
    last_day_purchases = [t for t in result.transactions if t.kind == "purchase" and t.day == last_day]
    assert last_day_purchases, "expected at least one purchase on the final simulated day"

    settlement_days = {t.day for t in result.transactions if t.kind == "settlement"}
    assert (last_day + 1) not in settlement_days, (
        "found a settlement on a day beyond the simulated run -- "
        "unexpected end-of-run auto-settlement was added"
    )

    total_pending_at_end = sum(
        a.balance for a in result.accounts if a.owner_type == "merchant_pending"
    )
    assert total_pending_at_end > 0, (
        "expected some unsettled pending balance at run end (last day's proceeds)"
    )


def test_merchant_settled_plus_pending_equals_total_purchase_proceeds():
    """Conservation check: since merchants have no spending behavior at
    all (Architecture.md/Memory.md), every dollar a merchant ever
    received via a successful purchase must be sitting in EITHER their
    settled account OR their pending account at run end -- never lost,
    never duplicated."""
    result = _engine(seed=7).run()

    proceeds_by_merchant: dict[str, float] = {}
    for t in result.transactions:
        if t.kind == "purchase":
            proceeds_by_merchant[t.to_id] = proceeds_by_merchant.get(t.to_id, 0.0) + t.amount

    settled_by_merchant = {a.owner_id: a.balance for a in result.accounts if a.owner_type == "merchant"}
    pending_by_merchant = {
        a.owner_id: a.balance for a in result.accounts if a.owner_type == "merchant_pending"
    }

    for merchant_id, proceeds in proceeds_by_merchant.items():
        total = settled_by_merchant.get(merchant_id, 0.0) + pending_by_merchant.get(merchant_id, 0.0)
        assert round(total, 2) == round(proceeds, 2), (
            f"{merchant_id}: settled+pending={total} != total purchase proceeds={proceeds}"
        )


# ---------------------------------------------------------------------------
# Determinism extends to the new ledger/settlement output (Rules.md #6)
# ---------------------------------------------------------------------------


def test_same_seed_produces_identical_ledger_entries_in_memory():
    result_a = _engine(seed=123).run()
    result_b = _engine(seed=123).run()

    def _flatten(result):
        return [
            (a.account_id, e.entry_id, e.entry_type, e.amount, e.balance_after, e.transaction_id)
            for a in result.accounts
            for e in a.ledger
        ]

    assert _flatten(result_a) == _flatten(result_b)


def test_settlement_and_ledger_draw_no_extra_nondeterminism_across_seeds():
    """Different seeds must still produce different ledger output (a
    sanity check that settlement/ledger logic isn't silently constant
    regardless of the RNG stream feeding purchases/salaries)."""
    result_a = _engine(seed=1).run()
    result_b = _engine(seed=2).run()

    def _flatten(result):
        return [(e.entry_id, e.amount, e.transaction_id) for a in result.accounts for e in a.ledger]

    assert _flatten(result_a) != _flatten(result_b)
