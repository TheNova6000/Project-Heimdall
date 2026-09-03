"""
Typed records for the Financial World Simulation (Phase 1).

Code style decision (Design.md "Code style"): plain stdlib `dataclasses`,
not Pydantic. Phase 1 has no validation/serialization needs that justify
a new dependency (Architecture.md: "no new heavy dependencies until a
real need appears"), and dataclasses are enough to keep records typed
and self-documenting.

These four records are exactly the ones Architecture.md's "Core data
model" section specifies for Phase 1 -- Account, Transaction, Event,
plus LedgerEntry as the natural unit of an Account's ledger. No other
record types are added; a richer taxonomy (refunds, chargebacks, retry
sequences, ...) is explicitly out of scope for Phase 1 (Rules.md #9,
Phases.md Phase 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LedgerEntry:
    """One line in an Account's ledger. Positive amount = credit, negative = debit."""

    entry_id: str
    account_id: str
    timestamp: str  # ISO 8601 UTC, per Design.md
    amount: float
    balance_after: float
    description: str


@dataclass
class Account:
    """
    A Bank account belonging to a Person or a Merchant.

    Phase 1 scope note: this is a single running balance plus a ledger,
    not a double-entry assets/liabilities ledger -- that split is
    explicitly Phase 2 scope (Architecture.md's Account definition;
    Phases.md Phase 2).
    """

    account_id: str
    bank_id: str
    owner_id: str  # a Person.person_id or Merchant.merchant_id
    owner_type: str  # "person" | "merchant"
    balance: float = 0.0
    ledger: list[LedgerEntry] = field(default_factory=list)


@dataclass
class Transaction:
    """
    The unit of output (Architecture.md). One row per attempted movement
    of money -- whether it succeeded or failed.

    `kind` follows Architecture.md's stated taxonomy exactly:
    salary | purchase | payment_failure. A failed purchase attempt is
    recorded with kind="payment_failure" rather than a separate
    kind+status pair, matching the spec's literal wording ("kind in
    {salary, purchase, payment_failure, ...}") and keeping the CSV flat.

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
