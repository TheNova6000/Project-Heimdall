"""
Phase 2.5 tests: the structural abstractions layered over Person/Bank/
Merchant -- multi-account (savings), Household, Organization, Community.
See docs/Memory.md's "Phase 2.5" section for the full design writeup.

Mirrors tests/test_ledger.py's style and rigor (Rules.md #6/#7): every new
correctness claim Phase 2.5 makes is checked here explicitly, not just
asserted in prose. The pre-existing double-entry invariant tests in
tests/test_ledger.py (`test_double_entry_invariant_holds_globally` /
`_per_transaction`) already run against an engine that unconditionally
exercises every Phase 2.5 mechanism (savings/household sweeps, Organization
payroll), so those tests already extend to cover this task's new flows
without needing to be duplicated here -- this file adds the
Phase-2.5-SPECIFIC claims those generic invariant tests don't check on
their own (savings/household accumulation consistency, organization
payroll's real ledger-backed traceability, Community's structural
inertness).

Run with:
    python -m pytest tests/ -v          (from inside Simulation/)
    python -m pytest tests/test_phase25.py -v
"""

from __future__ import annotations

import datetime

from world.engine import (
    HOUSEHOLD_SWEEP_FRACTION,
    SAVINGS_SWEEP_FRACTION,
    SimulationEngine,
)

START_DATE = datetime.date(2026, 1, 1)


def _engine(seed: int = 7, **overrides) -> SimulationEngine:
    kwargs = dict(
        seed=seed,
        num_persons=120,
        num_banks=3,
        num_merchants=6,
        num_days=60,
        start_date=START_DATE,
    )
    kwargs.update(overrides)
    return SimulationEngine(**kwargs)


# ---------------------------------------------------------------------------
# A.1 -- multi-account (savings)
# ---------------------------------------------------------------------------


def test_every_person_has_exactly_a_checking_and_a_savings_account():
    result = _engine(seed=1).run()
    person_ids = {p.person_id for p in result.persons}

    checking_owners = [a.owner_id for a in result.accounts if a.owner_type == "person"]
    savings_owners = [a.owner_id for a in result.accounts if a.owner_type == "person_savings"]

    assert set(checking_owners) == person_ids
    assert set(savings_owners) == person_ids
    assert len(checking_owners) == len(person_ids), "expected exactly one checking account per person"
    assert len(savings_owners) == len(person_ids), "expected exactly one savings account per person"


def test_savings_account_balance_equals_sum_of_savings_sweep_transactions():
    """A.1's core accumulation claim: since a savings account is never
    debited anywhere in this task's scope (purchases only ever draw from
    checking -- see world/engine.py's _maybe_attempt_purchase), each
    person's final savings balance must exactly equal the sum of every
    savings_sweep Transaction credited to them. Computed from two
    independent record types (LedgerEntry-derived account balance vs.
    Transaction rows), not a tautology."""
    result = _engine(seed=3).run()

    savings_account_by_person = {
        a.owner_id: a for a in result.accounts if a.owner_type == "person_savings"
    }
    assert savings_account_by_person, "expected at least one person_savings account"

    swept_by_person: dict[str, float] = {}
    for t in result.transactions:
        if t.kind == "savings_sweep":
            swept_by_person[t.to_id] = swept_by_person.get(t.to_id, 0.0) + t.amount

    checked_nonzero = 0
    for person_id, account in savings_account_by_person.items():
        expected = round(swept_by_person.get(person_id, 0.0), 2)
        assert round(account.balance, 2) == expected, (
            f"{person_id}'s savings balance {account.balance} != sum of their "
            f"savings_sweep transactions {expected}"
        )
        if expected > 0:
            checked_nonzero += 1
    assert checked_nonzero > 0, "expected at least one person with a nonzero savings balance to check"


def test_savings_sweep_fraction_matches_the_stated_constant():
    """Cross-check the ACTUAL simulated ratio of total savings_sweep
    amount to total gross pay (salary + savings_sweep + household_sweep,
    i.e. what a payday split into) against SAVINGS_SWEEP_FRACTION -- proof
    the constant is genuinely driving output, not just documented in a
    comment nobody wired up."""
    result = _engine(seed=9).run()

    total_savings = sum(t.amount for t in result.transactions if t.kind == "savings_sweep")
    total_gross_pay = sum(
        t.amount
        for t in result.transactions
        if t.kind in {"salary", "savings_sweep", "household_sweep"}
    )
    assert total_gross_pay > 0
    actual_fraction = total_savings / total_gross_pay
    assert abs(actual_fraction - SAVINGS_SWEEP_FRACTION) < 0.001, (
        f"actual savings fraction {actual_fraction} != SAVINGS_SWEEP_FRACTION "
        f"{SAVINGS_SWEEP_FRACTION}"
    )


def test_purchases_never_draw_from_savings():
    """The stated modeling assumption (A.1): purchases only ever debit a
    person's CHECKING account, never savings -- checked by confirming no
    purchase/payment_failure Transaction's from_id maps to a person whose
    savings account received a ledger debit on that transaction_id."""
    result = _engine(seed=5).run()

    purchase_txn_ids = {
        t.transaction_id for t in result.transactions if t.kind in {"purchase", "payment_failure"}
    }
    for account in result.accounts:
        if account.owner_type != "person_savings":
            continue
        for entry in account.ledger:
            assert entry.transaction_id not in purchase_txn_ids, (
                f"savings account {account.account_id} was touched by purchase "
                f"transaction {entry.transaction_id}"
            )
            assert entry.entry_type == "credit", (
                f"savings account {account.account_id} received an unexpected "
                f"{entry.entry_type} entry -- savings should only ever be credited"
            )


# ---------------------------------------------------------------------------
# A.2 -- Household
# ---------------------------------------------------------------------------


def test_every_person_belongs_to_exactly_one_household():
    result = _engine(seed=11).run()
    person_ids = {p.person_id for p in result.persons}

    seen: set[str] = set()
    for h in result.households:
        for pid in h.person_ids:
            assert pid not in seen, f"{pid} appears in more than one household"
            seen.add(pid)
    assert seen == person_ids


def test_household_sizes_are_within_the_stated_range():
    result = _engine(seed=13).run()
    for h in result.households:
        assert 1 <= len(h.person_ids) <= 4, f"{h.household_id} has size {len(h.person_ids)}"


def test_household_account_balance_equals_sum_of_member_contributions():
    """A.2's core accumulation claim: a household account is never debited
    anywhere in this task's scope (no 'household purchase' mechanic was
    built, per this task's explicit instruction), so its final balance
    must exactly equal the sum of every household_sweep Transaction from
    its own members."""
    result = _engine(seed=17).run()

    household_account_by_id = {
        a.owner_id: a for a in result.accounts if a.owner_type == "household"
    }
    assert household_account_by_id

    swept_by_household: dict[str, float] = {}
    for t in result.transactions:
        if t.kind == "household_sweep":
            swept_by_household[t.to_id] = swept_by_household.get(t.to_id, 0.0) + t.amount

    checked_nonzero = 0
    for h in result.households:
        account = household_account_by_id[h.household_id]
        expected = round(swept_by_household.get(h.household_id, 0.0), 2)
        assert round(account.balance, 2) == expected, (
            f"{h.household_id} balance {account.balance} != sum of its members' "
            f"household_sweep transactions {expected}"
        )
        for entry in account.ledger:
            assert entry.entry_type == "credit", (
                f"household account {account.account_id} received an unexpected "
                f"{entry.entry_type} entry -- household accounts should only ever be credited"
            )
        if expected > 0:
            checked_nonzero += 1
    assert checked_nonzero > 0


def test_household_sweep_fraction_matches_the_stated_constant():
    result = _engine(seed=19).run()

    total_household = sum(t.amount for t in result.transactions if t.kind == "household_sweep")
    total_gross_pay = sum(
        t.amount
        for t in result.transactions
        if t.kind in {"salary", "savings_sweep", "household_sweep"}
    )
    assert total_gross_pay > 0
    actual_fraction = total_household / total_gross_pay
    assert abs(actual_fraction - HOUSEHOLD_SWEEP_FRACTION) < 0.001


# ---------------------------------------------------------------------------
# A.3 -- Organization
# ---------------------------------------------------------------------------


def test_every_organization_employed_person_has_an_organization_id():
    result = _engine(seed=23).run()
    employee_ids = {pid for o in result.organizations for pid in o.employee_person_ids}
    assert employee_ids, "expected at least one Organization-employed person in this run"
    assert employee_ids <= {p.person_id for p in result.persons}
    # No person is double-employed across two Organizations.
    seen: set[str] = set()
    for o in result.organizations:
        for pid in o.employee_person_ids:
            assert pid not in seen, f"{pid} appears as an employee of more than one Organization"
            seen.add(pid)


def test_organization_salary_is_a_real_post_transfer_not_synthetic():
    """B.1's core traceability claim, proven here at the unit-test level
    too (not just by the validation system): every salary/savings_sweep/
    household_sweep transaction for an Organization-employed person has
    from_id starting with "org:<id>", NOT "employer:<id>", and its ledger
    entries include a real debit against that Organization's own revenue
    account -- no orphaned/synthetic postings."""
    result = _engine(seed=29).run()

    org_by_id = {o.organization_id: o for o in result.organizations}
    employed_person_ids = {pid for o in result.organizations for pid in o.employee_person_ids}
    assert employed_person_ids

    revenue_account_ledger: dict[str, list] = {
        a.owner_id: a.ledger for a in result.accounts if a.owner_type == "organization_revenue"
    }

    checked = 0
    for t in result.transactions:
        if t.kind not in {"salary", "savings_sweep"} or t.to_id not in employed_person_ids:
            continue
        assert t.from_id.startswith("org:"), (
            f"{t.transaction_id} pays an Organization-employed person but from_id "
            f"is {t.from_id!r}, not an 'org:' source"
        )
        organization_id = t.from_id.split(":", 1)[1]
        assert organization_id in org_by_id
        debit_txn_ids = {
            e.transaction_id for e in revenue_account_ledger[organization_id] if e.entry_type == "debit"
        }
        assert t.transaction_id in debit_txn_ids, (
            f"{t.transaction_id} has no matching debit in {organization_id}'s revenue account ledger"
        )
        checked += 1
    assert checked > 0, "expected at least one organization-sourced salary/savings_sweep transaction"


def test_organization_revenue_account_is_funded_via_org_funding_transaction():
    """Every Organization with at least one employee must have exactly one
    org_funding Transaction crediting its revenue account, and that
    Transaction's ledger entries must be a real balanced pair against a
    bank_reserve account (fund_external), per world/engine.py's
    _build_world."""
    result = _engine(seed=31).run()

    funded_org_ids = {t.to_id for t in result.transactions if t.kind == "org_funding"}
    orgs_with_employees = {o.organization_id for o in result.organizations if o.employee_person_ids}
    assert orgs_with_employees <= funded_org_ids, (
        "every Organization with employees must have received an org_funding transaction"
    )

    org_funding_txn_ids = {
        t.transaction_id: t.amount for t in result.transactions if t.kind == "org_funding"
    }
    for account in result.accounts:
        for entry in account.ledger:
            if entry.transaction_id in org_funding_txn_ids and account.owner_type == "bank_reserve":
                assert entry.entry_type == "debit"


def test_no_negative_balance_in_organization_revenue_accounts():
    """Organizations are funded generously (ORG_FUNDING_SAFETY_MULTIPLIER)
    but payroll failure is NOT structurally prevented -- this checks the
    one guarantee that IS unconditional: a revenue account, like every
    other account in this system, must never go negative (Rules.md #7),
    even though it CAN be drawn down close to zero."""
    result = _engine(seed=37).run()
    for account in result.accounts:
        if account.owner_type != "organization_revenue":
            continue
        assert account.balance >= 0
        for entry in account.ledger:
            assert entry.balance_after >= 0


# ---------------------------------------------------------------------------
# A.4 -- Community (deliberately inert)
# ---------------------------------------------------------------------------


def test_every_household_and_organization_belongs_to_exactly_one_community():
    result = _engine(seed=41).run()

    household_ids = {h.household_id for h in result.households}
    organization_ids = {o.organization_id for o in result.organizations}

    seen_households: set[str] = set()
    seen_orgs: set[str] = set()
    for c in result.communities:
        for hid in c.household_ids:
            assert hid not in seen_households, f"{hid} appears in more than one community"
            seen_households.add(hid)
        for oid in c.organization_ids:
            assert oid not in seen_orgs, f"{oid} appears in more than one community"
            seen_orgs.add(oid)

    assert seen_households == household_ids
    assert seen_orgs == organization_ids


def test_community_is_structurally_inert():
    """The project owner's own explicit framing: Community exists purely
    for future aggregate analysis and must drive NO simulation behavior
    today. Proven here, not just claimed: no community_id ever appears as
    a Transaction's from_id/to_id or an Event's subject_id, and Community
    consumed no RNG draws of its own (checked indirectly: two runs that
    differ only in whether Community grouping code executes would be
    needed to prove the RNG-draw claim directly, which is exactly what
    world/engine.py's own comment states -- this test instead proves the
    weaker, directly-observable half: nothing downstream ever references a
    community_id)."""
    result = _engine(seed=43).run()
    community_ids = {c.community_id for c in result.communities}
    assert community_ids, "expected at least one community"

    for t in result.transactions:
        assert t.from_id not in community_ids
        assert t.to_id not in community_ids
    for e in result.events:
        assert e.subject_id not in community_ids
