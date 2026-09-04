"""
Failure mechanisms -- Phase 3 ("Mechanism Engine", docs/Phases.md).

Before this phase, Truman had exactly ONE way a purchase attempt could
fail, hardcoded inline in world/engine.py's `_maybe_attempt_purchase()`:
`post_transfer()` (world/agents/bank.py) fails iff `balance_before <
amount`. This module formalizes that into a real, pluggable abstraction --
a `FailureMechanism` is anything that can decide, from a purchase
attempt's own visible state and nothing else (Architecture.md's "no
hidden global state" principle, applied here to failure causes too), that
THIS specific attempt fails, and why.

Deliberately NOT a generic, dynamically-loaded plugin system (this task's
own explicit instruction) -- just a small, real abstraction with a FIXED,
hand-written, causally-ordered list of mechanisms
(world/engine.py's `FAILURE_MECHANISMS`), evaluated in that order on every
purchase attempt (`SimulationEngine._evaluate_purchase_failure`). The
first mechanism whose `check()` fires wins and the attempt is recorded as
a `payment_failure` with NO money moved; a purchase attempt that clears
every mechanism proceeds to a real `post_transfer()` call.

Two mechanisms exist as of this phase:

- `InsufficientFundsMechanism` -- the ORIGINAL, sole Phase 1-2.5
  mechanism, migrated here with EXACTLY the same condition (see its own
  docstring): mirrors `world/agents/bank.py`'s `has_sufficient_balance`,
  the same function `post_transfer()` itself now calls, so the two call
  sites cannot silently drift apart. This is not itself a probability
  rule -- it is the literal ledger constraint Rules.md #7 requires.
- `ExpiredInstrumentMechanism` -- NEW this phase: a purchase attempt fails
  if the payer's Device (world/models.py) is past its own `expiry_day` as
  of the attempt's simulated day, REGARDLESS of balance. See its own
  docstring and docs/Memory.md's "Phase 3" section for the full
  provenance/design writeup, including why it is checked FIRST in
  `FAILURE_MECHANISMS` (causal ordering: a real payment network declines
  an expired card at the authorization step, before a balance is ever
  consulted).

Every mechanism's `check()` must be a PURE function of its
`PurchaseAttemptContext` argument -- no side effects, no RNG draws
(Rules.md #6: this framework's own evaluation consumes zero randomness;
every RNG draw that decides whether/how much a person attempts to spend,
and which device/merchant is involved, already happened before a
PurchaseAttemptContext is built -- see `_maybe_attempt_purchase`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from world.agents.bank import has_sufficient_balance


@dataclass(frozen=True)
class PurchaseAttemptContext:
    """
    Read-only view of exactly the state a FailureMechanism is allowed to
    see for one purchase attempt -- nothing about any other agent or any
    other attempt, matching Architecture.md's "no hidden global state"
    principle, applied here to this framework specifically. Built fresh
    by `SimulationEngine._maybe_attempt_purchase` for every attempt.
    """

    balance_before: float
    amount: float
    day: int  # simulated day index (0-based), same convention as
    # Transaction.day / world/models.py.
    device_expiry_day: int | None
    # The payer's Device's own `expiry_day` (world/models.py), or None if
    # this attempt has no resolvable device. In practice every Person
    # always has exactly one Device (docs/Memory.md's "Device" section),
    # so this should never actually be None on a real run -- but a
    # mechanism must handle it gracefully rather than assume it, since a
    # context is constructed by the engine, not guaranteed valid by this
    # module.


@dataclass(frozen=True)
class FailureOutcome:
    """
    What a FailureMechanism reports when it decides a purchase attempt
    should fail: the `Event.event_type` this cause should be recorded
    under (docs/Design.md's naming convention), plus any extra
    `Event.payload` keys this specific cause wants to carry.

    Follows the `retried_from`/`blocked_device` precedent already
    established in `world/engine.py`'s `_record()`: a mechanism-specific
    cause is carried as an ADDITIVE `Event.payload` key, never as a new
    `Transaction` dataclass field -- a new always-present field would add
    a column to every `transactions.csv` row on every run (Transaction
    rows are written via `dataclasses.asdict()` against a fixed
    fieldnames list), which would break byte-identical default output.
    `extra_payload` is empty for a mechanism (like InsufficientFunds) that
    needs no extra marker beyond its own distinct `event_type`.
    """

    event_type: str
    extra_payload: dict[str, object] = field(default_factory=dict)


class FailureMechanism(ABC):
    """
    One pluggable, independently-testable cause of a purchase attempt
    failing before any money moves.
    """

    @abstractmethod
    def check(self, ctx: PurchaseAttemptContext) -> FailureOutcome | None:
        """Return a FailureOutcome if this mechanism causes ctx's attempt
        to fail, else None. Must be a pure function of `ctx` -- see this
        module's docstring."""
        raise NotImplementedError


class InsufficientFundsMechanism(FailureMechanism):
    """
    The ORIGINAL, sole Phase 1-2.5 failure mechanism, migrated here with
    the EXACT SAME condition it always had: a purchase attempt fails iff
    `balance_before < amount` -- i.e. `not has_sufficient_balance(...)`,
    the identical predicate `world/agents/bank.py`'s `post_transfer()`
    itself enforces (both call sites share that one function, so they
    cannot silently drift apart -- see `has_sufficient_balance`'s own
    docstring). This is not a probability rule and carries no "provenance"
    label in the Rules.md #2 sense (research-grounded / modeling
    assumption / placeholder) -- it is the literal ledger constraint
    Rules.md #7 ("no negative balances, no fabricated money") requires,
    restated as a FailureMechanism rather than invented as one.

    Recorded exactly as before this phase: `event_type="purchase_failed"`,
    no extra payload key (Part A of this phase's task proves this
    refactor changes NOTHING about real output -- see docs/Memory.md's
    "Phase 3" section for the verbatim `diff -rq` proof).
    """

    def check(self, ctx: PurchaseAttemptContext) -> FailureOutcome | None:
        if has_sufficient_balance(ctx.balance_before, ctx.amount):
            return None
        return FailureOutcome(event_type="purchase_failed")


class ExpiredInstrumentMechanism(FailureMechanism):
    """
    NEW this phase: a purchase attempt fails if the payer's Device
    (world/models.py's `Device.expiry_day`) is already past its own
    validity window as of the attempt's simulated day -- REGARDLESS of
    whether the payer's balance is sufficient. See docs/Memory.md's
    "Phase 3" section for the full design writeup: `Device.issued_day`/
    `expiry_day` are assigned once, at world-generation time
    (`SimulationEngine._build_world`'s device-assignment pass), from
    `DEVICE_VALIDITY_PERIOD_DAYS_RANGE` (world/engine.py -- research-
    grounded window length, with a separately-named modeling assumption
    for how a device's residual life is positioned relative to simulated
    day 0).

    Checked FIRST in `world/engine.py`'s `FAILURE_MECHANISMS` list, ahead
    of `InsufficientFundsMechanism` -- a deliberate causal-ordering
    decision, not an arbitrary one: a real payment network declines an
    expired card at the authorization step itself, before the cardholder's
    available balance is ever consulted (an expired card is refused
    regardless of how much money is in the account behind it). Checking
    balance first would get the causal story backwards for any attempt
    where BOTH conditions happen to hold at once.

    Once a Device's `expiry_day` has passed, EVERY subsequent purchase
    attempt from it fails this way for the rest of the run -- there is no
    "device replacement"/reissuance mechanic (an honest, named scope
    limitation, not an oversight; see docs/Memory.md). This mirrors the
    existing `block_device()` live-loop mechanism's own "no un-blocking"
    semantics (world/engine.py) -- once true, permanently true for the
    remainder of a run, by the same kind of real-world logic (a card
    genuinely stays expired until reissued, exactly like a device
    genuinely stays blocked until un-reviewed, which Heimdall's own real
    Risk domain also never does).

    Recorded with a distinct `event_type`
    (`purchase_failed_expired_instrument`, never `purchase_failed`) and an
    `extra_payload` key (`expired_instrument: True`) -- `Transaction.kind`
    itself stays `"payment_failure"`, unchanged, following the exact
    precedent `block_device()`'s own device-blocked failure already set
    (docs/Design.md's "Naming conventions" section): this is still
    honestly "an attempted purchase that failed," just with a distinct
    cause, and Heimdall's own real `FAILURE_TAXONOMY`
    (`financial_system/recovery/signals.py`, read-only -- never modified
    by this task) already names a category for exactly this cause:
    `"expired"`. Reusing `payment_failure` as the `kind` (rather than
    inventing a new kind value) is the more faithful mapping onto
    Heimdall's own real vocabulary, not a shortcut -- a future bridge
    session extending `financial_system/bridges/simulation_bridge.py`
    (untouched by this task) could map this mechanism's
    `expired_instrument` payload marker directly onto
    `failure_reason="expired"` without renaming anything on either side.
    """

    def check(self, ctx: PurchaseAttemptContext) -> FailureOutcome | None:
        if ctx.device_expiry_day is None:
            return None
        if ctx.day < ctx.device_expiry_day:
            return None
        return FailureOutcome(
            event_type="purchase_failed_expired_instrument",
            extra_payload={"expired_instrument": True},
        )
