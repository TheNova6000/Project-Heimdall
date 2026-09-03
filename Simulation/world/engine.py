"""
Simulation engine -- ties agents + clock into one deterministic run.

Architecture.md's simulation loop, implemented literally, with one
addition (Phase 2 -- see below):

    for each tick (one simulated day):
        settle yesterday's merchant proceeds (Phase 2)
        for each Person:
            maybe receive income
            maybe attempt a purchase
            if attempted and balance insufficient: emit payment_failure
        write all events/transactions for this tick to the event log

Determinism (Rules.md #6): exactly one `random.Random(seed)` instance
exists per run, created here and threaded through every call that needs
randomness. No other module calls the global `random` module or reads
wall-clock time. Entities are iterated in a fixed, seed-independent order
(creation order) every tick, so the same seed always produces the same
sequence of RNG draws and therefore byte-identical output.

No hidden global state (Architecture.md): every agent decision function
takes that agent's own state (balance, income, risk_preference) as
arguments -- the engine reads an account's current balance from the Bank
and passes only that in, never anything about other agents.

## Phase 2 additions (Phases.md, Phase 2)

- Income and purchases now move money through `world/agents/bank.py`'s
  new double-entry primitives (`Bank.fund_external`, `post_transfer`)
  instead of Phase 1's single-entry `Bank.credit`/`Bank.debit` -- see
  that module's docstring for the full design.
- A new `_run_settlement` step runs once per simulated day, before that
  day's Person loop: it sweeps every Merchant's pending (received-but-
  not-yet-settled) balance into their settled/spendable account, one
  simulated day after it was received (T+1 -- see `_run_settlement`'s
  docstring for this timing rule's provenance).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass

from world.agents.bank import Bank, post_transfer
from world.agents.merchant import MERCHANT_CATEGORIES, Merchant
from world.agents.person import Person
from world.clock import SimClock
from world.models import Account, Event, Transaction

# ---------------------------------------------------------------------------
# Population-generation constants (Phase 1: creating a plausible starting
# world, not simulating behavior -- still subject to Rules.md #2).
# ---------------------------------------------------------------------------

# MODELING ASSUMPTION, informally grounded in the standard stylized fact in
# income-distribution economics that individual incomes are approximately
# log-normally distributed (e.g. Aitchison & Brown, "The Lognormal
# Distribution", 1957) -- used here for its right-skewed *shape* only
# (few high earners, many modest earners), NOT calibrated against any real
# income dataset or currency, per Rules.md #3 (no external data) and #5
# (don't overclaim). mu/sigma chosen so monthly incomes mostly fall in a
# plausible few-hundred-to-few-thousand-unit range.
INCOME_LOGNORMAL_MU = 8.3
INCOME_LOGNORMAL_SIGMA = 0.5
INCOME_MIN = 300.0
INCOME_MAX = 25000.0

# MODELING ASSUMPTION: a person's opening balance is a random fraction
# (10%-100%) of their own monthly income -- i.e. everyone starts with
# somewhere between a few days' and a full month's income already banked.
# Arbitrary but named starting condition, not derived from data.
OPENING_BALANCE_FRACTION_RANGE = (0.1, 1.0)

# MODELING ASSUMPTION: risk_preference is drawn uniformly over [0, 1] --
# no claim that real risk preferences are uniformly distributed across a
# population; uniform is the least-assumption-laden choice available for a
# trait Architecture.md defines but does not specify a distribution for.
RISK_PREFERENCE_RANGE = (0.0, 1.0)

# MODELING ASSUMPTION: payday is a person's own fixed day-of-month, drawn
# uniformly from 1-28 (28 chosen, not 31, so "payday" is always a valid
# date in every month including February -- an implementation constraint,
# not a behavioral claim).
PAYDAY_RANGE = (1, 28)

EMPLOYER_PREFIX = "employer"  # synthetic, unmodeled money source for salary


@dataclass
class SimulationResult:
    """Everything a run produced, handed back to run_simulation.py to write out."""

    persons: list[Person]
    banks: list[Bank]
    merchants: list[Merchant]
    accounts: list[Account]  # flattened across all banks, in creation order
    transactions: list[Transaction]
    events: list[Event]
    seed: int
    num_days: int


@dataclass
class _IdCounters:
    """Monotonic counters -> deterministic, human-scannable IDs (Design.md)."""

    account: int = 0
    ledger_entry: int = 0
    transaction: int = 0
    event: int = 0

    def next_account_id(self) -> str:
        self.account += 1
        return f"acct_{self.account:06x}"

    def next_ledger_id(self) -> str:
        self.ledger_entry += 1
        return f"ldg_{self.ledger_entry:08x}"

    def next_txn_id(self) -> str:
        self.transaction += 1
        return f"txn_{self.transaction:08x}"

    def next_event_id(self) -> str:
        self.event += 1
        return f"evt_{self.event:08x}"


class SimulationEngine:
    def __init__(
        self,
        seed: int,
        num_persons: int,
        num_banks: int,
        num_merchants: int,
        num_days: int,
        start_date,
    ) -> None:
        self.seed = seed
        self.num_persons = num_persons
        self.num_banks = num_banks
        self.num_merchants = num_merchants
        self.num_days = num_days
        self.rng = random.Random(seed)  # the ONE randomness source for this run
        self.clock = SimClock(start_date=start_date)
        self.ids = _IdCounters()

        self.transactions: list[Transaction] = []
        self.events: list[Event] = []

        self.banks: list[Bank] = []
        self.merchants: list[Merchant] = []
        self.persons: list[Person] = []
        # account_id -> owning Bank, so the engine can post to an account by
        # id without every caller needing to know which bank it lives in
        self._account_bank: dict[str, Bank] = {}
        # person_id -> their account_id, merchant_id -> their (settled)
        # account_id
        self.person_account: dict[str, str] = {}
        self.merchant_account: dict[str, str] = {}
        # Phase 2: merchant_id -> their pending-settlement account_id
        # (purchase proceeds land here first; see world/agents/merchant.py
        # and _run_settlement below)
        self.merchant_pending_account: dict[str, str] = {}

        self._build_world()

    # ------------------------------------------------------------------
    # World generation
    # ------------------------------------------------------------------
    def _build_world(self) -> None:
        for i in range(1, self.num_banks + 1):
            bank = Bank(bank_id=f"bank_{i:02d}", name=f"Bank {i}")
            # Phase 2: every Bank gets one asset-side reserve account
            # before anything else can be funded through it -- see
            # world/agents/bank.py's module docstring ("Why a
            # bank_reserve asset account").
            reserve_account_id = self.ids.next_account_id()
            bank.open_reserve_account(reserve_account_id)
            self._account_bank[reserve_account_id] = bank
            self.banks.append(bank)

        for i in range(1, self.num_merchants + 1):
            bank = self.rng.choice(self.banks)
            merchant_id = f"merchant_{i:04d}"
            category = self.rng.choice(MERCHANT_CATEGORIES)
            account_id = self.ids.next_account_id()
            bank.open_account(account_id, owner_id=merchant_id, owner_type="merchant")
            self._account_bank[account_id] = bank
            self.merchant_account[merchant_id] = account_id
            # Phase 2: a second account per merchant holding proceeds
            # that have been received but not yet settled -- see
            # world/agents/merchant.py and _run_settlement below.
            pending_account_id = self.ids.next_account_id()
            bank.open_account(pending_account_id, owner_id=merchant_id, owner_type="merchant_pending")
            self._account_bank[pending_account_id] = bank
            self.merchant_pending_account[merchant_id] = pending_account_id
            self.merchants.append(
                Merchant(
                    merchant_id=merchant_id,
                    name=f"Merchant {i}",
                    bank_account_id=account_id,
                    category=category,
                    pending_account_id=pending_account_id,
                )
            )

        for i in range(1, self.num_persons + 1):
            person_id = f"person_{i:05d}"
            income = min(
                INCOME_MAX,
                max(
                    INCOME_MIN,
                    self.rng.lognormvariate(INCOME_LOGNORMAL_MU, INCOME_LOGNORMAL_SIGMA),
                ),
            )
            income = round(income, 2)
            opening_fraction = self.rng.uniform(*OPENING_BALANCE_FRACTION_RANGE)
            opening_balance = round(income * opening_fraction, 2)
            risk_preference = round(self.rng.uniform(*RISK_PREFERENCE_RANGE), 3)
            payday = self.rng.randint(*PAYDAY_RANGE)

            bank = self.rng.choice(self.banks)
            account_id = self.ids.next_account_id()
            bank.open_account(
                account_id,
                owner_id=person_id,
                owner_type="person",
                opening_balance=opening_balance,
            )
            self._account_bank[account_id] = bank
            self.person_account[person_id] = account_id

            self.persons.append(
                Person(
                    person_id=person_id,
                    name=f"Person {i}",
                    income_monthly=income,
                    balance=opening_balance,
                    risk_preference=risk_preference,
                    payday=payday,
                )
            )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def run(self) -> SimulationResult:
        for _day in range(self.num_days):
            self._run_one_day()
            self.clock.advance()

        accounts = [acct for bank in self.banks for acct in bank.accounts.values()]
        return SimulationResult(
            persons=self.persons,
            banks=self.banks,
            merchants=self.merchants,
            accounts=accounts,
            transactions=self.transactions,
            events=self.events,
            seed=self.seed,
            num_days=self.num_days,
        )

    def _run_one_day(self) -> None:
        # Phase 2: settle yesterday's merchant proceeds BEFORE today's
        # purchases add anything new to a pending account -- this
        # ordering is what makes the sweep exactly T+1 (see
        # _run_settlement's docstring).
        self._run_settlement()

        day_of_month = self.clock.day_of_month
        # Fixed iteration order (list order = creation order = person_id
        # order) every tick, on every run -- required for determinism.
        for person in self.persons:
            self._maybe_pay_income(person, day_of_month)
            self._maybe_attempt_purchase(person)

    # -- settlement (Phase 2) ------------------------------------------------
    def _run_settlement(self) -> None:
        """
        Sweep every Merchant's pending (received-but-not-yet-settled)
        balance into their settled/spendable account.

        RESEARCH-GROUNDED, WITH A NAMED SIMPLIFICATION (Phase 3 update,
        docs/Research.md "Part B"; was previously an unqualified modeling
        assumption). Real card-network settlement is consistently
        reported, across multiple independent industry sources, to take
        on the order of one to three business days after a transaction:
        Stripe's own public documentation states "settlement typically
        takes one to three business days after the transaction" for
        card payments (Stripe, "Payment settlement explained: how it
        works and how long it takes", stripe.com/resources/more/
        payment-settlement-explained-how-it-works-and-how-long-it-takes,
        accessed 2026), and multiple payments-industry processor
        explainers (e.g. Clearly Payments, "How Long Do Credit Card
        Payments Take to Settle?", clearlypayments.com) independently
        report the same 1-3 business day window. That range is what
        grounds "not instant, on the order of a day or more" as a real
        fact about card settlement, not an invented one.

        The SPECIFIC choice of exactly T+1 (the low/fastest end of that
        range, applied uniformly with no variation) remains a named
        MODELING ASSUMPTION, not itself research-derived: no source
        above says every merchant settles in exactly 1 day, and this
        simulation does not model the network/risk-tier/country factors
        that make real settlement land anywhere in that 1-3 day range.
        T+1 was kept (over, say, a random 1-3 day draw) because it is
        the simplest value that still makes "received" and "settled"
        genuinely distinct states -- that distinction is the entire
        point of this Phase 2 feature (this task's brief: "rather than
        money just appearing usable instantly") -- while adding a random
        settlement delay would perturb the RNG draw sequence for
        purchases/salary that Phase 2 deliberately avoided disturbing
        (see Memory.md's Phase 2 section), a change this narrow research
        finding does not by itself justify.

        Because this runs at the very start of `_run_one_day`, before
        that day's purchases can add anything new to a pending account,
        whatever sits in a merchant's pending account right now is
        entirely proceeds from strictly earlier days (in practice, just
        yesterday, since this sweeps everything every single day and
        never partially). Sweeping the whole balance is therefore
        exactly T+1, not "eventually."

        A fixed batch time (03:00 UTC), not RNG-sampled: settlement is a
        systemic process run once a day, not an individual agent's
        probabilistic decision (contrast `_event_timestamp()` below), so
        this draws no randomness and cannot itself be a source of
        nondeterminism beyond the same fixed creation-order iteration
        used everywhere else in this engine.

        Honest caveat (see Memory.md): proceeds received on the final
        simulated day of a run are never swept (there is no "day
        num_days" tick to sweep them on) -- they remain visible in the
        pending account/balance at run end. This is treated as realistic
        (a real business always has some in-flight receivables), not a
        bug, and is checked by tests/test_ledger.py rather than hidden.
        """
        timestamp = self.clock.timestamp(hour=3, minute=0, second=0)
        for merchant in self.merchants:
            pending_account_id = self.merchant_pending_account[merchant.merchant_id]
            pending_bank = self._account_bank[pending_account_id]
            pending_balance = pending_bank.balance_of(pending_account_id)
            if pending_balance <= 0:
                continue

            settled_account_id = self.merchant_account[merchant.merchant_id]
            settled_bank = self._account_bank[settled_account_id]
            balance_before = pending_balance  # the pending account's own
            # balance before this sweep -- by construction (full sweep,
            # every day) this equals `amount` below; see Memory.md for
            # why that's an expected, near-tautological artifact of a
            # full-sweep design, not a bug (the same honesty Phase 1
            # already applied to payment_failure's balance_before check).

            txn_id = self.ids.next_txn_id()
            post_transfer(
                pending_bank,
                pending_account_id,
                settled_bank,
                settled_account_id,
                pending_balance,
                timestamp,
                description=f"settlement for {merchant.merchant_id}",
                entry_ids=self._new_entry_pair(),
                transaction_id=txn_id,
            )
            self._record(
                transaction_id=txn_id,
                kind="settlement",
                timestamp=timestamp,
                from_id=f"pending:{merchant.merchant_id}",
                to_id=merchant.merchant_id,
                amount=pending_balance,
                balance_before=balance_before,
                event_type="settlement_completed",
            )

    # -- income -----------------------------------------------------------
    def _maybe_pay_income(self, person: Person, day_of_month: int) -> None:
        amount = person.maybe_receive_income(day_of_month, self.rng)
        if amount <= 0:
            return
        account_id = self.person_account[person.person_id]
        bank = self._account_bank[account_id]
        balance_before = bank.balance_of(account_id)
        # MODELING ASSUMPTION (money origin, not a rule violation of
        # Rules.md #7): salary has to enter the modeled economy from
        # somewhere. This project does not model employer institutions
        # (Architecture.md scopes agents to Person/Bank/Merchant only), so
        # income is credited from a synthetic, unmodeled "employer:<id>"
        # source rather than from another agent's account. Rules.md #7's
        # "no fabricated money" concerns money appearing mid-transaction
        # between modeled agents (e.g. a debit failing but a credit still
        # happening) -- this is a distinct, standard convention for
        # closed-population economic simulations: income is exogenous.
        # As of Phase 2 this is a real double-entry posting
        # (`Bank.fund_external`: Debit this bank's own reserve asset
        # account / Credit the person's deposit account), not the
        # unmatched single ledger entry Phase 1 wrote.
        timestamp = self._event_timestamp()
        txn_id = self.ids.next_txn_id()
        bank.fund_external(
            account_id,
            amount,
            timestamp,
            description=f"salary for {person.person_id}",
            entry_ids=self._new_entry_pair(),
            transaction_id=txn_id,
        )
        from_id = f"{EMPLOYER_PREFIX}:{person.person_id}"
        self._record(
            transaction_id=txn_id,
            kind="salary",
            timestamp=timestamp,
            from_id=from_id,
            to_id=person.person_id,
            amount=amount,
            balance_before=balance_before,
            event_type="salary_received",
        )

    # -- purchase -----------------------------------------------------------
    def _maybe_attempt_purchase(self, person: Person) -> None:
        account_id = self.person_account[person.person_id]
        bank = self._account_bank[account_id]
        balance = bank.balance_of(account_id)

        if not person.wants_to_spend(balance, self.rng):
            return

        amount = person.purchase_amount(self.rng)
        merchant = self.rng.choice(self.merchants)
        # Phase 2: purchase proceeds land in the merchant's PENDING
        # account, not their spendable one directly -- see
        # _run_settlement and world/agents/merchant.py.
        merchant_pending_account_id = self.merchant_pending_account[merchant.merchant_id]
        merchant_bank = self._account_bank[merchant_pending_account_id]

        timestamp = self._event_timestamp()
        balance_before = bank.balance_of(account_id)
        txn_id = self.ids.next_txn_id()
        succeeded = post_transfer(
            bank,
            account_id,
            merchant_bank,
            merchant_pending_account_id,
            amount,
            timestamp,
            description=f"purchase at {merchant.merchant_id}",
            entry_ids=self._new_entry_pair(),
            transaction_id=txn_id,
        )

        if succeeded:
            self._record(
                transaction_id=txn_id,
                kind="purchase",
                timestamp=timestamp,
                from_id=person.person_id,
                to_id=merchant.merchant_id,
                amount=amount,
                balance_before=balance_before,
                event_type="purchase_succeeded",
            )
        else:
            # THE mechanism this project exists to demonstrate: this
            # failure is emitted because `post_transfer` just observed
            # balance_before < amount for THIS agent, on THIS attempt --
            # not because a category-level probability was drawn
            # independently of any agent state (contrast PRD.md's
            # description of financial_system's retry_would_succeed).
            self._record(
                transaction_id=txn_id,
                kind="payment_failure",
                timestamp=timestamp,
                from_id=person.person_id,
                to_id=merchant.merchant_id,
                amount=amount,
                balance_before=balance_before,
                event_type="purchase_failed",
            )

    # -- shared recording helpers --------------------------------------------
    def _new_entry_pair(self) -> tuple[str, str]:
        """Two fresh, monotonic ledger-entry ids for one balanced double-
        entry posting (see world/agents/bank.py)."""
        return (self.ids.next_ledger_id(), self.ids.next_ledger_id())

    def _event_timestamp(self) -> str:
        # MODELING ASSUMPTION: intraday time-of-day is sampled uniformly
        # across a plausible "awake" window (7am-10pm UTC) purely so that
        # multiple same-day events don't all share one identical timestamp.
        # No claim is made about real payment-timing patterns (that is
        # explicitly out of scope -- Phases.md Phase 4 territory). Drawn
        # from the run's single seeded RNG, so still fully deterministic.
        hour = self.rng.randint(7, 22)
        minute = self.rng.randint(0, 59)
        second = self.rng.randint(0, 59)
        return self.clock.timestamp(hour=hour, minute=minute, second=second)

    def _record(
        self,
        *,
        transaction_id: str,
        kind: str,
        timestamp: str,
        from_id: str,
        to_id: str,
        amount: float,
        balance_before: float,
        event_type: str,
    ) -> None:
        # Phase 2: transaction_id is now generated by the caller (before
        # this is invoked), not here -- callers need the id up front to
        # pass as the `transaction_id` on the balanced ledger-entry pair
        # they post via world/agents/bank.py's primitives, so every
        # LedgerEntry can be traced back to the Transaction row that
        # caused it.
        txn = Transaction(
            transaction_id=transaction_id,
            timestamp=timestamp,
            day=self.clock.day,
            from_id=from_id,
            to_id=to_id,
            amount=amount,
            kind=kind,
            balance_before=balance_before,
        )
        self.transactions.append(txn)

        # json.dumps with sort_keys=True keeps payloads byte-identical
        # across runs with the same seed (dict key order would otherwise
        # be an unnecessary source of nondeterminism-looking diffs).
        payload = json.dumps(
            {
                "transaction_id": txn.transaction_id,
                "amount": amount,
                "from_id": from_id,
                "to_id": to_id,
                "balance_before": balance_before,
            },
            sort_keys=True,
        )
        self.events.append(
            Event(
                event_id=self.ids.next_event_id(),
                event_type=event_type,
                subject_id=from_id,
                occurred_at=timestamp,
                payload=payload,
            )
        )
