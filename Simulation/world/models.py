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
    # | "person_savings" | "household" | "organization_revenue" (Phase 2.5 --
    # see world/agents/bank.py's module docstring and docs/Memory.md's
    # "Phase 2.5" section for what each new type represents)
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

    `device_id` (new -- see docs/Memory.md's "Device" section) is set
    ONLY for a person-initiated transaction (`purchase`/`payment_failure`
    -- the device the payer actually transacted from, resolved via
    world/engine.py's `self.person_device`). Every other kind (`salary`,
    `settlement`, `savings_sweep`, `household_sweep`, `org_funding`) is a
    systemic/automatic money movement, not something a person taps a
    device to do -- `device_id` is left as the empty string for those,
    deliberately, rather than inventing a device-of-record for a
    transaction no one is holding a device for.
    """

    transaction_id: str
    timestamp: str
    day: int  # simulated day index (0-based) -- convenience for stats
    from_id: str
    to_id: str
    amount: float
    kind: str  # salary | purchase | payment_failure
    balance_before: float
    device_id: str = ""


@dataclass
class Household:
    """
    Phase 2.5 structural abstraction (docs/Memory.md's "Phase 2.5" section
    has the full design rationale). Per Architecture.md's guiding principle
    ("Person/Bank/Merchant are the only agents with probabilistic decision
    logic"), Household is NOT a new decision-maker -- it has no probability
    functions of its own. It is a grouping of existing Person ids plus one
    real, ledger-backed shared bank account (`household_account_id`) that a
    fixed fraction of each member's salary is swept into (see
    `world/engine.py`'s `_maybe_pay_income` / `HOUSEHOLD_SWEEP_FRACTION`).
    No "household purchase" mechanic exists -- the account only ever grows.
    """

    household_id: str
    person_ids: list[str]
    household_account_id: str


@dataclass
class Organization:
    """
    Phase 2.5 structural abstraction. Groups Persons as "employees" and
    gives the group one real, ledger-backed bank account
    (`revenue_account_id`) representing revenue that is exogenous to this
    simulation (same honest convention Phase 1 used for the synthetic
    `employer:<person_id>` source, just now backed by a real account -- see
    `world/agents/bank.py`'s `fund_external` and `world/engine.py`'s
    org-sourced salary path in `_maybe_pay_income`). Like Household, this
    is a structural/ledger abstraction over existing Person agents, not a
    new probabilistic decision-maker -- it has no behavior of its own
    beyond holding a balance that payroll draws down and that gets funded
    once at world-generation time.
    """

    organization_id: str
    name: str
    employee_person_ids: list[str]
    revenue_account_id: str


@dataclass
class Community:
    """
    Phase 2.5 structural abstraction, deliberately minimal per the project
    owner's own framing (docs/Memory.md's "Phase 2.5" section): a grouping
    of Household and Organization ids with NO money-movement mechanic and
    no probabilistic behavior at all. It exists purely so a future session
    could aggregate/analyze at the community level if a real reason to do
    so ever appears -- it drives nothing in this simulation today. This is
    intentional, not a placeholder for a cut feature; inventing a
    "community effect" just to make this feel more complete would be
    exactly the unjustified mechanism Rules.md #2/#5 warn against.
    """

    community_id: str
    household_ids: list[str]
    organization_ids: list[str]


@dataclass
class Device:
    """
    The device a Person transacts from (new -- see docs/Memory.md's
    "Device" section for the full design rationale). Every Person is
    linked to exactly one Device at world-generation time (world/engine.py's
    device-assignment pass, run right after Household grouping) -- this
    matches the real Heimdall schema's 1-payment-uses-1-device shape
    (`financial_system/risk/signals.py` reads exactly this kind of
    Device<->Customer linkage to compute its device-sharing risk signal).

    Like Household/Organization/Community, Device is NOT a new
    probabilistic decision-maker (Architecture.md's guiding principle:
    "Person/Bank/Merchant are the only agents with probabilistic decision
    logic") -- it is an ownership/identity structure. `owner_person_ids`
    has exactly one entry for a personal device, or two-or-more for a
    household's shared "primary" device -- the ONE legitimate sharing
    mechanism this simulation models (see world/engine.py's
    `DEVICE_HOUSEHOLD_SHARING_FRACTION` for its exact provenance). A
    shared device's owners are always members of the same Household --
    device sharing never crosses household boundaries, and no fraud-ring
    or other cross-household sharing mechanism exists anywhere in this
    simulation (explicitly out of scope; see docs/Research.md Part C.1 and
    docs/Memory.md's "Device" section).
    """

    device_id: str
    fingerprint: str  # deterministic, derived from device_id -- not a real
    # hardware fingerprint algorithm, just a stand-in identity string
    # (Simulation has no device-hardware model at all)
    owner_person_ids: list[str]


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
