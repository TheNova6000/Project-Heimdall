"""
Typed records for the Financial World Simulation.

Code style decision (Design.md "Code style"): plain stdlib `dataclasses`,
not Pydantic. Phase 1 has no validation/serialization needs that justify
a new dependency (Architecture.md: "no new heavy dependencies until a
real need appears"), and dataclasses are enough to keep records typed
and self-documenting. Phase 2 keeps this convention rather than
introducing a new one.

These records are the ones Architecture.md's "Core data model" section
specifies -- Account, Transaction, Event, plus LedgerEntry as the
natural unit of an Account's ledger. A richer taxonomy (refunds,
chargebacks, retry sequences, ...) is still explicitly out of scope
(Rules.md #9, Phases.md Phase 4).

## Phase 2 change: LedgerEntry is now a real double-entry line

Phase 1's LedgerEntry stored one signed `amount` per account per
movement (positive=credit, negative=debit) with no link back to what
caused it and no matching entry anywhere else -- e.g. a salary credit
had no corresponding debit anywhere in the ledger. That was fine for
Phase 1's single-running-balance scope, but it is not double-entry
bookkeeping.

Phase 2 (Phases.md: "Real double-entry-style ledger for Bank
(assets/liabilities, not just a balance number)") changes LedgerEntry
to the standard double-entry shape: an explicit `entry_type`
("debit"/"credit"), an *unsigned* `amount` magnitude, and a
`transaction_id` linking every entry back to the Transaction/settlement
event that produced it. Every economic movement in `world/agents/bank.py`
now posts entries in balanced pairs (one debit + one credit of equal
magnitude), so "sum of all debit amounts == sum of all credit amounts"
holds across the whole ledger at all times -- this is the double-entry
invariant `tests/test_ledger.py` proves. `Account.balance` remains a
live, derived/cached value updated alongside the ledger (kept for
Phase 1 code and CSV-output compatibility), but the ledger is now the
source of truth: `Account.balance` is always reconstructable by
replaying `Account.ledger` from zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LedgerEntry:
    """
    One line in an Account's double-entry ledger (Phase 2).

    `amount` is an unsigned magnitude; `entry_type` ("debit" | "credit")
    says which side of standard accounting it lands on. Every entry is
    always posted as part of a balanced pair (see `world/agents/bank.py`
    `_post_pair` docstring) carrying the same `transaction_id`, so a
    reader can always find an entry's counterpart.

    Sign convention (standard double-entry bookkeeping, applied per
    account's `owner_type` -- see `Bank._post` in `world/agents/bank.py`):
    for a liability account (person/merchant/merchant deposits), a debit
    *decreases* the balance and a credit *increases* it (matches Phase
    1's `Bank.debit`/`Bank.credit` naming); for an asset account (a
    bank's own reserve account, Phase 2's new `owner_type="bank_reserve"`),
    it's the reverse -- debit increases, credit decreases.
    """

    entry_id: str
    account_id: str
    timestamp: str  # ISO 8601 UTC, per Design.md
    entry_type: str  # "debit" | "credit"
    amount: float  # unsigned magnitude
    balance_after: float
    description: str
    transaction_id: str  # links this entry to the Transaction (or the
    # synthetic settlement operation) that produced it -- its balanced
    # counterpart entry elsewhere in the ledger shares this same id.


@dataclass
class Account:
    """
    A Bank account belonging to a Person, a Merchant, or (Phase 2, new)
    a Bank itself (a "bank_reserve" asset account -- see
    `world/agents/bank.py`).

    `balance` is a live cache kept in sync with `ledger` on every post
    (Phase 1 behavior, kept for compatibility -- see models.py module
    docstring); `ledger` is the source of truth as of Phase 2.
    """

    account_id: str
    bank_id: str
    owner_id: str  # a Person.person_id, Merchant.merchant_id, or (for a
    # reserve account) the owning Bank.bank_id
    owner_type: str  # "person" | "merchant" | "merchant_pending" | "bank_reserve"
    balance: float = 0.0
    ledger: list[LedgerEntry] = field(default_factory=list)


@dataclass
class Transaction:
    """
    The unit of output (Architecture.md). One row per attempted movement
    of money -- whether it succeeded or failed.

    `kind` follows Architecture.md's stated taxonomy
    (salary | purchase | payment_failure | ...) and Phase 2 adds exactly
    one new value it explicitly authorizes ("basic settlement between
    Merchant and Bank", Phases.md Phase 2): `settlement`, emitted when a
    merchant's previously-received, not-yet-usable purchase proceeds
    move from pending to settled (see `world/engine.py`
    `_run_settlement`). A failed purchase attempt is recorded with
    kind="payment_failure" rather than a separate kind+status pair,
    matching the spec's literal wording and keeping the CSV flat.

    `balance_before` is one field beyond the architecture's minimal list,
    added because it is the single most direct evidence for or against
    this project's central hypothesis (PRD.md "Why"): it lets
    stats/report.py show that payment_failure rows are exactly the rows
    where balance_before < amount, i.e. the failure is mechanically
    caused by the agent's own state, not drawn from an independent
    per-category coin flip. This is additive instrumentation, not a
    taxonomy expansion, so it does not conflict with Rules.md #9.
    """

    transaction_id: str
    timestamp: str
    day: int  # simulated day index (0-based) -- convenience for stats
    from_id: str
    to_id: str
    amount: float
    kind: str  # salary | purchase | payment_failure
    balance_before: float


@dataclass
class Event:
    """
    Append-only event log entry, mirroring Heimdall's event-sourcing
    discipline (Architecture.md). Emitted alongside (not instead of) each
    Transaction, plus a small number of lifecycle events (simulation
    start/end). `payload` is a JSON-encoded string rather than nested
    columns, per Design.md ("JSON only where a record's shape is
    genuinely nested... a flat CSV would lose information") applied
    within a single CSV row.
    """

    event_id: str
    event_type: str
    subject_id: str
    occurred_at: str
    payload: str
