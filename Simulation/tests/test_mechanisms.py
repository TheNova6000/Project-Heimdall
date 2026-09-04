"""
Tests for world/mechanisms.py -- Phase 3 ("Mechanism Engine",
docs/Phases.md). See docs/Memory.md's "Phase 3" section for the full
design writeup.

Covers, per this task's explicit ask:
  - InsufficientFundsMechanism's condition is EXACTLY
    world/agents/bank.py's has_sufficient_balance -- the same predicate
    post_transfer() itself now calls -- proving Part A's framework
    refactor is behavior-preserving at the unit level (the CLI-level,
    whole-run byte-identical proof is documented in docs/Memory.md's
    "Phase 3" section via a real, verbatim `diff -rq` run, not repeated
    here as a pytest since it requires two full separate CLI invocations
    and a filesystem diff -- see that section for the exact command/
    result).
  - ExpiredInstrumentMechanism fires iff `day >= device_expiry_day`,
    REGARDLESS of balance -- checked both as a pure unit test and directly
    against real simulation output.
  - FAILURE_MECHANISMS' causal ordering (ExpiredInstrumentMechanism
    checked before InsufficientFundsMechanism) is real, not just
    documented in a comment.
  - An expired-device purchase attempt posts zero ledger entries, exactly
    like an insufficient-funds failure.

Run with:
    python -m pytest tests/ -v          (from inside Simulation/)
    python -m pytest tests/test_mechanisms.py -v
"""

from __future__ import annotations

import datetime

from world.agents.bank import has_sufficient_balance
from world.engine import DEVICE_VALIDITY_PERIOD_DAYS_RANGE, FAILURE_MECHANISMS, SimulationEngine
from world.mechanisms import (
    ExpiredInstrumentMechanism,
    InsufficientFundsMechanism,
    PurchaseAttemptContext,
)

START_DATE = datetime.date(2026, 1, 1)


def _engine(seed: int = 21, **overrides) -> SimulationEngine:
    kwargs = dict(seed=seed, num_persons=600, num_banks=3, num_merchants=8, num_days=150, start_date=START_DATE)
    kwargs.update(overrides)
    return SimulationEngine(**kwargs)


# ---------------------------------------------------------------------------
# InsufficientFundsMechanism -- unit-level proof it's EXACTLY the old check
# ---------------------------------------------------------------------------


def test_insufficient_funds_mechanism_matches_has_sufficient_balance_exactly():
    """The migrated mechanism's condition must be identical to
    has_sufficient_balance across a range of cases, including the exact
    boundary (amount == balance, which must NOT fail, matching
    post_transfer's own pre-Phase-3 `amount > from_account.balance`
    check)."""
    mechanism = InsufficientFundsMechanism()
    cases = [
        (100.0, 50.0),  # plenty
        (100.0, 100.0),  # exact boundary -- must succeed (amount <= balance)
        (100.0, 100.01),  # just over -- must fail
        (0.0, 0.01),  # broke
        (0.0, 0.0),  # zero/zero -- succeeds (0 <= 0)
    ]
    for balance, amount in cases:
        ctx = PurchaseAttemptContext(balance_before=balance, amount=amount, day=0, device_expiry_day=None)
        outcome = mechanism.check(ctx)
        expected_fail = not has_sufficient_balance(balance, amount)
        assert (outcome is not None) == expected_fail, (
            f"balance={balance} amount={amount}: mechanism outcome={outcome} disagrees with "
            f"has_sufficient_balance={has_sufficient_balance(balance, amount)}"
        )
        if outcome is not None:
            # Byte-identical-to-before-Phase-3 payload shape: no extra key.
            assert outcome.event_type == "purchase_failed"
            assert outcome.extra_payload == {}


def test_insufficient_funds_mechanism_ignores_device_state():
    """InsufficientFundsMechanism is purely a balance check -- device_
    expiry_day must have zero effect on its own decision (that's
    ExpiredInstrumentMechanism's job, checked separately and BEFORE this
    one in FAILURE_MECHANISMS)."""
    mechanism = InsufficientFundsMechanism()
    for expiry_day in (None, -5, 0, 5, 1000):
        ctx = PurchaseAttemptContext(balance_before=1000.0, amount=10.0, day=5, device_expiry_day=expiry_day)
        assert mechanism.check(ctx) is None


# ---------------------------------------------------------------------------
# ExpiredInstrumentMechanism -- unit-level
# ---------------------------------------------------------------------------


def test_expired_instrument_mechanism_fires_exactly_at_and_after_expiry_day():
    mechanism = ExpiredInstrumentMechanism()
    # Strictly before expiry_day: does not fire.
    assert mechanism.check(PurchaseAttemptContext(1e9, 1.0, day=9, device_expiry_day=10)) is None
    # AT expiry_day: fires (no longer valid AS OF this day).
    outcome = mechanism.check(PurchaseAttemptContext(1e9, 1.0, day=10, device_expiry_day=10))
    assert outcome is not None
    assert outcome.event_type == "purchase_failed_expired_instrument"
    assert outcome.extra_payload == {"expired_instrument": True}
    # After expiry_day: fires.
    assert mechanism.check(PurchaseAttemptContext(1e9, 1.0, day=11, device_expiry_day=10)) is not None


def test_expired_instrument_mechanism_fires_regardless_of_balance():
    """THE defining property distinguishing this mechanism from
    InsufficientFundsMechanism: fires even with an enormous balance."""
    mechanism = ExpiredInstrumentMechanism()
    ctx = PurchaseAttemptContext(balance_before=1_000_000.0, amount=1.0, day=100, device_expiry_day=50)
    assert mechanism.check(ctx) is not None


def test_expired_instrument_mechanism_none_when_no_device_resolved():
    """Handles device_expiry_day=None gracefully -- should not happen on a
    real run (every Person has exactly one Device), but a mechanism must
    not crash or misfire on it."""
    mechanism = ExpiredInstrumentMechanism()
    ctx = PurchaseAttemptContext(balance_before=0.0, amount=1000.0, day=100, device_expiry_day=None)
    assert mechanism.check(ctx) is None


# ---------------------------------------------------------------------------
# Ordering -- ExpiredInstrumentMechanism checked FIRST in FAILURE_MECHANISMS
# ---------------------------------------------------------------------------


def test_failure_mechanisms_ordering_expired_instrument_first():
    assert [type(m) for m in FAILURE_MECHANISMS] == [ExpiredInstrumentMechanism, InsufficientFundsMechanism]


def test_expired_instrument_wins_over_insufficient_funds_when_both_would_fire():
    """When an attempt has BOTH an expired device AND an insufficient
    balance, the recorded cause must be expired_instrument -- the causal-
    ordering decision (docs/Memory.md's "Phase 3" section) is real, not
    just documented in a comment."""
    ctx = PurchaseAttemptContext(balance_before=1.0, amount=1000.0, day=10, device_expiry_day=5)
    first_fired = next(o for o in (m.check(ctx) for m in FAILURE_MECHANISMS) if o is not None)
    assert first_fired.event_type == "purchase_failed_expired_instrument"


# ---------------------------------------------------------------------------
# Device validity window -- provenance-backed constant, applied correctly
# ---------------------------------------------------------------------------


def test_device_expiry_day_always_positive_and_validity_window_matches_constant():
    """Every Device's expiry_day > 0 (valid on day 0, by construction --
    see world/engine.py's _draw_device_validity docstring) and its full
    validity period (expiry_day - issued_day) falls inside
    DEVICE_VALIDITY_PERIOD_DAYS_RANGE."""
    result = _engine(seed=5, num_days=10).run()
    lo, hi = DEVICE_VALIDITY_PERIOD_DAYS_RANGE
    assert result.devices, "expected at least one device"
    for d in result.devices:
        assert d.expiry_day > 0, f"{d.device_id} has non-positive expiry_day {d.expiry_day}"
        validity = d.expiry_day - d.issued_day
        assert lo <= validity <= hi, f"{d.device_id}: validity {validity} outside {(lo, hi)}"


# ---------------------------------------------------------------------------
# Against real simulation output
# ---------------------------------------------------------------------------


def test_expired_instrument_failures_only_occur_on_or_after_the_devices_own_expiry_day():
    """The mechanical proof, checked directly against real output: every
    real purchase_failed_expired_instrument transaction's own simulated
    day is >= its payer's device's real expiry_day."""
    result = _engine().run()
    device_expiry_by_id = {d.device_id: d.expiry_day for d in result.devices}

    checked = 0
    for t, e in zip(result.transactions, result.events):
        if e.event_type != "purchase_failed_expired_instrument":
            continue
        assert t.day >= device_expiry_by_id[t.device_id], (
            f"{t.transaction_id} on day {t.day} fired expired_instrument, but {t.device_id}'s "
            f"expiry_day is {device_expiry_by_id[t.device_id]} (still valid)"
        )
        checked += 1
    assert checked > 0, "expected at least one expired-instrument failure in this run"


def test_no_non_expired_outcome_for_an_already_expired_devices_purchase_attempt():
    """The complementary direction: any purchase/payment_failure attempt
    from an already-expired device (t.day >= its expiry_day) must be
    recorded as expired_instrument -- never a plain successful purchase or
    an ordinary insufficient-funds failure."""
    result = _engine().run()
    device_expiry_by_id = {d.device_id: d.expiry_day for d in result.devices}

    checked = 0
    for t, e in zip(result.transactions, result.events):
        if t.kind not in ("purchase", "payment_failure") or not t.device_id:
            continue
        expiry_day = device_expiry_by_id.get(t.device_id)
        if expiry_day is None or t.day < expiry_day:
            continue
        assert e.event_type == "purchase_failed_expired_instrument", (
            f"{t.transaction_id} on day {t.day} used device {t.device_id} (expired day {expiry_day}) "
            f"but was recorded as {e.event_type!r}"
        )
        checked += 1
    assert checked > 0, "expected at least one purchase attempt from an already-expired device"


def test_expired_instrument_failure_posts_zero_ledger_entries():
    """Same guarantee as an insufficient-funds failure: no money moves --
    confirmed explicitly, not just assumed from post_transfer never being
    called."""
    result = _engine().run()
    expired_txn_ids = {
        t.transaction_id for t, e in zip(result.transactions, result.events)
        if e.event_type == "purchase_failed_expired_instrument"
    }
    assert expired_txn_ids
    ledger_txn_ids = {entry.transaction_id for a in result.accounts for entry in a.ledger}
    assert not (expired_txn_ids & ledger_txn_ids), "an expired-instrument failure has a matching ledger entry"


def test_expired_instrument_failures_can_have_sufficient_balance():
    """THE causal-distinctness proof: at least one real expired-instrument
    failure has balance_before >= amount -- i.e. it would have SUCCEEDED
    under InsufficientFundsMechanism alone, proving this mechanism is a
    genuinely independent cause, not a relabeled balance failure."""
    result = _engine().run()
    expired_failures = [
        t for t, e in zip(result.transactions, result.events)
        if e.event_type == "purchase_failed_expired_instrument"
    ]
    assert expired_failures
    assert any(t.balance_before >= t.amount for t in expired_failures), (
        "expected at least one expired-instrument failure where the payer had enough balance -- "
        "the mechanical proof this mechanism is causally distinct from balance"
    )


# ---------------------------------------------------------------------------
# Determinism (Rules.md #6)
# ---------------------------------------------------------------------------


def test_same_seed_produces_identical_device_validity_windows():
    result_a = _engine(seed=99, num_days=10).run()
    result_b = _engine(seed=99, num_days=10).run()
    windows_a = [(d.device_id, d.issued_day, d.expiry_day) for d in result_a.devices]
    windows_b = [(d.device_id, d.issued_day, d.expiry_day) for d in result_b.devices]
    assert windows_a == windows_b


def test_different_seeds_produce_different_device_validity_windows():
    result_a = _engine(seed=1, num_days=10).run()
    result_b = _engine(seed=2, num_days=10).run()
    windows_a = [(d.device_id, d.issued_day, d.expiry_day) for d in result_a.devices]
    windows_b = [(d.device_id, d.issued_day, d.expiry_day) for d in result_b.devices]
    assert windows_a != windows_b
