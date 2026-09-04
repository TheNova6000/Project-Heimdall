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
from world.models import Account, Community, Device, Event, Household, Organization, Transaction

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

# ---------------------------------------------------------------------------
# Phase 2.5 -- structural abstractions (Household, Organization, Community).
# See docs/Memory.md's "Phase 2.5" section for the full design rationale.
# Per Architecture.md's guiding principle, none of these introduce a new
# probabilistic DECISION-MAKER -- they are account/grouping structures over
# the same three agent types (Person/Bank/Merchant) that already exist; the
# only new *behavior* is where a slice of an existing salary payment is
# routed (still governed entirely by Person.maybe_receive_income's existing
# probability rule -- these constants only affect the split of an amount
# that rule already decided to pay).
# ---------------------------------------------------------------------------

# MODELING ASSUMPTION: a fixed 15% of every salary payment is swept into the
# person's own savings account instead of their checking account, before any
# household sweep (below) is applied. Loosely motivated by the common
# personal-finance rule of thumb "save roughly 15-20% of income" (e.g. the
# well-known "50/30/20" budgeting guideline popularized by Elizabeth
# Warren's "All Your Worth", 2005) as a defensible, memorable round number --
# this was NOT independently verified against real household savings-rate
# data for this task (that would need its own dedicated research pass, out
# of this task's scope per its own instructions), so it stays a named
# MODELING ASSUMPTION, not a citation dressed up as research-grounded.
SAVINGS_SWEEP_FRACTION = 0.15

# MODELING ASSUMPTION: a further fixed 10% of every salary payment is swept
# into the person's household's shared account (see Household below),
# applied ON TOP OF (not instead of) the savings sweep above -- i.e. a
# person's gross pay splits 75% checking / 15% savings / 10% household by
# construction (checking gets the exact remainder: 1 - SAVINGS_SWEEP_FRACTION
# - HOUSEHOLD_SWEEP_FRACTION). Chosen smaller than the savings fraction
# because household pooling is modeled as a secondary behavior layered on
# top of a person's own saving, not a replacement for it. Applies uniformly
# regardless of household size, including a size-1 "household" (see
# HOUSEHOLD_SIZE_WEIGHTS below) -- for a single-person household this sweep
# is practically indistinguishable from a second personal savings-like
# account; that is a deliberate, harmless degenerate case of treating every
# household uniformly, not a hidden special rule.
HOUSEHOLD_SWEEP_FRACTION = 0.10

# MODELING ASSUMPTION: household size is drawn from a simple, named discrete
# distribution weighted toward small households (1-4 persons). This task's
# brief permitted an OPTIONAL bounded WebSearch for real household-size-
# distribution stats to justify this instead; that search was not done in
# this session (judged not worth the scope for a purely structural,
# behaviorally-inert-beyond-the-sweep grouping) -- these weights are
# deliberately labeled an honest, uncited assumption, not dressed up as
# research-grounded. Round numbers, not fit to any dataset.
HOUSEHOLD_SIZE_WEIGHTS: dict[int, float] = {1: 0.30, 2: 0.35, 3: 0.20, 4: 0.15}

# MODELING ASSUMPTION: roughly half the population is employed by a modeled
# Organization (real, ledger-backed payroll -- see Organization below); the
# other half keeps Phase 1/2's original synthetic "employer:<person_id>"
# convention unchanged. 0.5 is a round, defensible split chosen so BOTH
# salary-payment code paths are meaningfully exercised in every run, not
# because real employment-by-organization-size data was consulted.
ORG_MEMBERSHIP_FRACTION = 0.5

# MODELING ASSUMPTION: target average employees per Organization, used only
# to decide how many Organizations to create (see _build_world). An
# arbitrary, named round number, not derived from real firm-size data.
ORG_TARGET_SIZE = 25

# MODELING ASSUMPTION: each Organization's revenue account is funded ONCE,
# at world-generation time, with a buffer sized to comfortably cover that
# org's own full-run payroll (that org's employees' combined monthly income,
# scaled to the run's length in months, times this safety multiplier) -- a
# deliberate choice to fund generously so payroll failure is RARE in a
# typical run, NOT to structurally prevent it: `post_transfer` (world/
# agents/bank.py) still returns False, and `_maybe_pay_income` below still
# records a real `payment_failure`, if an Organization's revenue account
# genuinely can't cover a given payday. A smaller population-to-multiplier
# ratio, or a run longer than this buffer anticipates, CAN still produce a
# real organization payroll failure -- that possibility is intentionally
# left open, not engineered away (this task's explicit request).
ORG_FUNDING_SAFETY_MULTIPLIER = 1.2

# MODELING ASSUMPTION: households and organizations are grouped into a
# small, fixed number of named "communities" purely for future aggregate
# reporting -- Community has NO money-movement mechanic of its own (see
# world/models.py's Community docstring and docs/Memory.md's "Phase 2.5"
# section for why this is deliberately inert). 5 is an arbitrary round
# number, not derived from any real geographic/community-size data.
NUM_COMMUNITIES = 5

# ---------------------------------------------------------------------------
# Device -- see docs/Memory.md's "Device" section for the full design
# rationale. Every Person gets exactly one Device at world-generation time;
# the ONE legitimate sharing mechanism modeled is a household's members
# optionally sharing the household's "primary" device (see world/models.py's
# Device docstring). This is deliberately NOT a fraud/ring mechanism -- no
# is_fraud flag, no cross-household sharing, no fraud-driven device reuse
# exists anywhere in this simulation (docs/Research.md Part C.1 already
# covers why that stays out of scope as design-only).
# ---------------------------------------------------------------------------

# MODELING ASSUMPTION: for each household with 2+ members, one member (the
# first, in household-membership order -- an arbitrary but deterministic
# choice, not itself a probabilistic decision) is the household's "primary"
# device holder. Every OTHER member of that household independently has a
# 30% chance of transacting from that same shared primary device instead of
# getting their own personal device. Chosen as a defensible minority-but-
# substantial fraction: real multi-person households commonly do have one
# shared device (a family tablet/computer used for online purchases)
# alongside individual phones, but most members still mostly transact from
# their OWN device -- 30% keeps sharing a real, observable minority pattern
# rather than either the dominant case or a vanishingly rare one. This is
# NOT derived from any real device-sharing survey (that would need its own
# dedicated research pass, out of this task's scope) -- named honestly as an
# uncited assumption, same style as ORG_MEMBERSHIP_FRACTION/SAVINGS_SWEEP_
# FRACTION above. A single-person household (see HOUSEHOLD_SIZE_WEIGHTS)
# has no "other member" to draw for, so it always ends up with exactly one
# personal device -- a harmless degenerate case of the same rule, not a
# special case.
DEVICE_HOUSEHOLD_SHARING_FRACTION = 0.3


@dataclass
class SimulationResult:
    """Everything a run produced, handed back to run_simulation.py to write out."""

    persons: list[Person]
    banks: list[Bank]
    merchants: list[Merchant]
    households: list[Household]  # Phase 2.5
    organizations: list[Organization]  # Phase 2.5
    communities: list[Community]  # Phase 2.5
    devices: list[Device]  # Device (see docs/Memory.md's "Device" section)
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
    device: int = 0

    def next_account_id(self) -> str:
        self.account += 1
        return f"acct_{self.account:06x}"

    def next_device_id(self) -> str:
        self.device += 1
        return f"dev_{self.device:06x}"

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

        # Phase 2.5: Household/Organization/Community registries and the
        # per-person lookups _maybe_pay_income needs (see docs/Memory.md's
        # "Phase 2.5" section).
        self.households: list[Household] = []
        self.organizations: list[Organization] = []
        self.communities: list[Community] = []
        self.household_by_id: dict[str, Household] = {}
        self.organization_by_id: dict[str, Organization] = {}
        self.person_savings_account: dict[str, str] = {}
        self.person_household: dict[str, str] = {}  # person_id -> household_id
        self.person_organization: dict[str, str] = {}  # person_id -> organization_id
        # (only present for the ORG_MEMBERSHIP_FRACTION of persons who
        # belong to one -- absent, not None, for everyone else)
        self.org_bank: dict[str, Bank] = {}  # organization_id -> its Bank

        # Device: every person maps to exactly one device_id (their own, or
        # their household's shared "primary" device -- see
        # DEVICE_HOUSEHOLD_SHARING_FRACTION above and the device-assignment
        # pass at the end of _build_world).
        self.devices: list[Device] = []
        self.person_device: dict[str, str] = {}  # person_id -> device_id

        # Live-Risk-loop support (new -- see "Live-loop support" section
        # below and `block_device()`'s own docstring): a device_id lands in
        # this set ONLY via an explicit `block_device()` call -- nothing in
        # `_build_world()`/`run()`/`_run_one_day()` ever adds to it, so it
        # is always empty for a normal run (confirmed by grep -- see
        # `docs/Memory.md`'s entry for this addition). `_maybe_attempt_
        # purchase()`'s own device-blocked check consults this set, and
        # only this set.
        self.blocked_devices: set[str] = set()

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

        # Phase 2.5 A.3: create Organizations' bank accounts now (employee
        # lists start empty; membership is decided per-person below, and
        # the revenue account is funded once, after the Person loop, when
        # every employee's income is known -- see the end of this method).
        num_organizations = max(1, round((self.num_persons * ORG_MEMBERSHIP_FRACTION) / ORG_TARGET_SIZE))
        for i in range(1, num_organizations + 1):
            bank = self.rng.choice(self.banks)
            organization_id = f"org_{i:03d}"
            revenue_account_id = self.ids.next_account_id()
            bank.open_account(revenue_account_id, owner_id=organization_id, owner_type="organization_revenue")
            self._account_bank[revenue_account_id] = bank
            self.org_bank[organization_id] = bank
            org = Organization(
                organization_id=organization_id,
                name=f"Organization {i}",
                employee_person_ids=[],
                revenue_account_id=revenue_account_id,
            )
            self.organizations.append(org)
            self.organization_by_id[organization_id] = org

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

            # Phase 2.5 A.3: organization membership -- one more per-person
            # RNG draw in the existing fixed iteration order (creation
            # order), right alongside this person's other core traits. Only
            # decides WHICH money-source pays this person's salary later
            # (_maybe_pay_income); it is not itself a new probabilistic
            # behavior rule beyond "does this person belong to an org."
            if self.organizations and self.rng.random() < ORG_MEMBERSHIP_FRACTION:
                org = self.rng.choice(self.organizations)
                org.employee_person_ids.append(person_id)
                self.person_organization[person_id] = org.organization_id

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

            # Phase 2.5 A.1: a second, savings account per person. Opens at
            # zero -- no "opening savings balance" concept was requested,
            # only the ongoing salary-sweep mechanism (see
            # SAVINGS_SWEEP_FRACTION / _maybe_pay_income below).
            savings_account_id = self.ids.next_account_id()
            bank.open_account(savings_account_id, owner_id=person_id, owner_type="person_savings")
            self._account_bank[savings_account_id] = bank
            self.person_savings_account[person_id] = savings_account_id

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

        # Phase 2.5 A.3: fund each Organization's revenue account once, now
        # that every employee (and their income) is known. Uses
        # fund_external -- the same primitive/pattern bank_reserve funding
        # already uses -- per this task's explicit instruction; see
        # ORG_FUNDING_SAFETY_MULTIPLIER's docstring above for the buffer's
        # exact provenance/rationale. Recorded as a real Transaction (kind=
        # "org_funding") so it stays traceable, UNLIKE Person/Merchant
        # opening balances, which deliberately bypass the ledger entirely
        # (see world/agents/bank.py's module docstring, "Opening balances
        # are still out of ledger scope") -- an organization's revenue is a
        # modeled external inflow the task asked to make ledger-real, not a
        # world-generation initial condition.
        funding_timestamp = self.clock.timestamp(hour=0, minute=0, second=0)
        income_by_person = {p.person_id: p.income_monthly for p in self.persons}
        for org in self.organizations:
            if not org.employee_person_ids:
                continue
            total_monthly_payroll = sum(income_by_person[pid] for pid in org.employee_person_ids)
            buffer = round(
                total_monthly_payroll * (self.num_days / 30.0) * ORG_FUNDING_SAFETY_MULTIPLIER, 2
            )
            bank = self.org_bank[org.organization_id]
            txn_id = self.ids.next_txn_id()
            bank.fund_external(
                org.revenue_account_id,
                buffer,
                funding_timestamp,
                description=f"external revenue funding for {org.organization_id}",
                entry_ids=self._new_entry_pair(),
                transaction_id=txn_id,
            )
            self._record(
                transaction_id=txn_id,
                kind="org_funding",
                timestamp=funding_timestamp,
                from_id=f"external_revenue:{org.organization_id}",
                to_id=org.organization_id,
                amount=buffer,
                balance_before=0.0,
                event_type="organization_funded",
            )

        # Phase 2.5 A.2: group persons into Households sequentially, in
        # creation order (person_id order), by repeatedly drawing a target
        # household size from HOUSEHOLD_SIZE_WEIGHTS (see that constant's
        # docstring for provenance). This is a SEPARATE pass over the
        # already-built self.persons list, rather than interleaved with the
        # loop above, specifically so a household-size decision doesn't
        # perturb the per-person RNG draw sequence (income/opening_balance/
        # risk/payday/org-membership) that loop already consumed -- keeps
        # this addition's blast radius on existing per-person outcomes as
        # small as possible.
        idx = 0
        household_num = 0
        sizes = list(HOUSEHOLD_SIZE_WEIGHTS.keys())
        weights = list(HOUSEHOLD_SIZE_WEIGHTS.values())
        while idx < len(self.persons):
            household_num += 1
            size = self.rng.choices(sizes, weights=weights, k=1)[0]
            size = min(size, len(self.persons) - idx)
            members = self.persons[idx : idx + size]
            idx += size
            household_id = f"household_{household_num:05d}"
            # The household account opens at whichever Bank the first
            # member's own checking account lives at -- an arbitrary,
            # RNG-free choice (spending another RNG draw here was judged
            # unnecessary complexity for a purely structural account).
            first_member_account_id = self.person_account[members[0].person_id]
            bank = self._account_bank[first_member_account_id]
            household_account_id = self.ids.next_account_id()
            bank.open_account(household_account_id, owner_id=household_id, owner_type="household")
            self._account_bank[household_account_id] = bank
            member_ids = [m.person_id for m in members]
            for pid in member_ids:
                self.person_household[pid] = household_id
            household = Household(
                household_id=household_id,
                person_ids=member_ids,
                household_account_id=household_account_id,
            )
            self.households.append(household)
            self.household_by_id[household_id] = household

        # Device: assign exactly one Device to every Person (docs/Memory.md's
        # "Device" section). A SEPARATE pass, after Household grouping, for
        # the same reason Household grouping is itself a separate pass from
        # the main Person loop above: it genuinely needs Household membership
        # to already exist, and keeping it out of the per-person loop means
        # it cannot perturb the RNG draw sequence any earlier code already
        # depends on. Iterates households in creation order, and each
        # household's members in their existing (already-deterministic)
        # list order, so this pass's own RNG draws happen in a fixed,
        # seed-independent order every run.
        #
        # For each household: its first member is the "primary" device
        # holder (arbitrary, deterministic -- no RNG spent choosing who).
        # Every OTHER member independently has a DEVICE_HOUSEHOLD_SHARING_
        # FRACTION chance of sharing that same primary device instead of
        # getting their own. A member who does NOT share gets a fresh
        # personal device (owner_person_ids == [that one person]). This is
        # the ONLY device-sharing mechanism in this simulation -- no
        # cross-household sharing, no fraud-ring mechanism, no is_fraud
        # flag (explicitly out of scope, see DEVICE_HOUSEHOLD_SHARING_
        # FRACTION's docstring above and docs/Research.md Part C.1).
        for household in self.households:
            members = household.person_ids
            primary_id = members[0]
            sharers = [primary_id]
            for pid in members[1:]:
                if self.rng.random() < DEVICE_HOUSEHOLD_SHARING_FRACTION:
                    sharers.append(pid)

            primary_device_id = self.ids.next_device_id()
            primary_device = Device(
                device_id=primary_device_id,
                fingerprint=f"fp_{primary_device_id}",
                owner_person_ids=list(sharers),
            )
            self.devices.append(primary_device)
            for pid in sharers:
                self.person_device[pid] = primary_device_id

            for pid in members[1:]:
                if pid in sharers:
                    continue
                own_device_id = self.ids.next_device_id()
                own_device = Device(
                    device_id=own_device_id,
                    fingerprint=f"fp_{own_device_id}",
                    owner_person_ids=[pid],
                )
                self.devices.append(own_device)
                self.person_device[pid] = own_device_id

        # Phase 2.5 A.4: Communities -- a deliberately inert grouping of
        # Household/Organization ids into NUM_COMMUNITIES buckets,
        # round-robin by creation order. Pure structural bookkeeping, not a
        # behavioral decision, so it draws NOTHING from self.rng. See
        # world/models.py's Community docstring and docs/Memory.md's
        # "Phase 2.5" section for why this drives no simulation behavior.
        community_household_ids: list[list[str]] = [[] for _ in range(NUM_COMMUNITIES)]
        community_org_ids: list[list[str]] = [[] for _ in range(NUM_COMMUNITIES)]
        for i, household in enumerate(self.households):
            community_household_ids[i % NUM_COMMUNITIES].append(household.household_id)
        for i, org in enumerate(self.organizations):
            community_org_ids[i % NUM_COMMUNITIES].append(org.organization_id)
        for i in range(NUM_COMMUNITIES):
            self.communities.append(
                Community(
                    community_id=f"community_{i + 1:02d}",
                    household_ids=community_household_ids[i],
                    organization_ids=community_org_ids[i],
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
            households=self.households,
            organizations=self.organizations,
            communities=self.communities,
            devices=self.devices,
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

        checking_account_id = self.person_account[person.person_id]
        checking_bank = self._account_bank[checking_account_id]
        savings_account_id = self.person_savings_account[person.person_id]
        savings_bank = self._account_bank[savings_account_id]
        household_id = self.person_household[person.person_id]
        household_account_id = self.household_by_id[household_id].household_account_id
        household_bank = self._account_bank[household_account_id]

        # Phase 2.5 A.1/A.2: gross pay splits deterministically into three
        # components -- see SAVINGS_SWEEP_FRACTION/HOUSEHOLD_SWEEP_FRACTION's
        # module-level docstrings for provenance. The two sweep amounts are
        # rounded independently and checking takes the exact remainder, so
        # the three always sum to precisely `amount` -- no stray cents lost
        # or created by rounding.
        savings_amount = round(amount * SAVINGS_SWEEP_FRACTION, 2)
        household_amount = round(amount * HOUSEHOLD_SWEEP_FRACTION, 2)
        checking_amount = round(amount - savings_amount - household_amount, 2)

        timestamp = self._event_timestamp()
        organization_id = self.person_organization.get(person.person_id)

        if organization_id is not None:
            # Phase 2.5 A.3: this person's salary is real, ledger-backed
            # payroll from their Organization's revenue account (see
            # world/models.py's Organization docstring). Checked
            # atomically against the FULL amount up front -- rather than
            # letting checking succeed and savings/household fail
            # separately -- so a payday either happens in full or not at
            # all, mirroring purchase's all-or-nothing pattern instead of
            # introducing a new partial-failure shape this project has
            # never had.
            org = self.organization_by_id[organization_id]
            org_bank = self.org_bank[organization_id]
            from_id = f"org:{organization_id}"
            org_balance = org_bank.balance_of(org.revenue_account_id)
            if org_balance < amount:
                # THE genuine emergent possibility this task's brief asked
                # for: an Organization's own revenue account couldn't cover
                # payroll. Recorded exactly like a purchase's
                # payment_failure (same kind, same mechanical "balance_
                # before < amount" proof) -- just with the Organization's
                # revenue account as the insufficient balance instead of a
                # Person's checking account. ORG_FUNDING_SAFETY_MULTIPLIER's
                # docstring states plainly this is meant to be rare, not
                # structurally impossible.
                txn_id = self.ids.next_txn_id()
                self._record(
                    transaction_id=txn_id,
                    kind="payment_failure",
                    timestamp=timestamp,
                    from_id=from_id,
                    to_id=person.person_id,
                    amount=amount,
                    balance_before=org_balance,
                    event_type="salary_failed",
                )
                return
            source_bank, source_account_id = org_bank, org.revenue_account_id
        else:
            # Unchanged Phase 1/2 convention for the non-Organization half
            # of the population -- see EMPLOYER_PREFIX and Bank.
            # fund_external's own docstring. MODELING ASSUMPTION (money
            # origin, not a Rules.md #7 violation): income is credited from
            # a synthetic, unmodeled "employer:<id>" source because this
            # project does not model every employer as its own agent.
            from_id = f"{EMPLOYER_PREFIX}:{person.person_id}"
            source_bank, source_account_id = None, None

        self._post_and_record_leg(
            kind="salary",
            event_type="salary_received",
            from_id=from_id,
            to_id=person.person_id,
            amount=checking_amount,
            timestamp=timestamp,
            target_bank=checking_bank,
            target_account_id=checking_account_id,
            source_bank=source_bank,
            source_account_id=source_account_id,
        )
        self._post_and_record_leg(
            kind="savings_sweep",
            event_type="savings_swept",
            from_id=from_id,
            to_id=person.person_id,
            amount=savings_amount,
            timestamp=timestamp,
            target_bank=savings_bank,
            target_account_id=savings_account_id,
            source_bank=source_bank,
            source_account_id=source_account_id,
        )
        self._post_and_record_leg(
            kind="household_sweep",
            event_type="household_swept",
            from_id=from_id,
            to_id=household_id,
            amount=household_amount,
            timestamp=timestamp,
            target_bank=household_bank,
            target_account_id=household_account_id,
            source_bank=source_bank,
            source_account_id=source_account_id,
        )

    def _post_and_record_leg(
        self,
        *,
        kind: str,
        event_type: str,
        from_id: str,
        to_id: str,
        amount: float,
        timestamp: str,
        target_bank: Bank,
        target_account_id: str,
        source_bank: Bank | None,
        source_account_id: str | None,
    ) -> None:
        """
        Post one balanced leg of a payday (the checking, savings, or
        household portion) and record it as its own Transaction/Event --
        shared by both the Organization-sourced (`post_transfer`) and
        synthetic-employer-sourced (`Bank.fund_external`) salary paths in
        `_maybe_pay_income`. `source_bank`/`source_account_id` being None
        selects `fund_external` (money entering from this bank's own
        reserve); both set selects `post_transfer` (money moving from a
        real Organization revenue account). `amount <= 0` is a no-op, same
        convention as the underlying primitives.
        """
        if amount <= 0:
            return
        balance_before = target_bank.balance_of(target_account_id)
        txn_id = self.ids.next_txn_id()
        if source_bank is not None and source_account_id is not None:
            ok = post_transfer(
                source_bank,
                source_account_id,
                target_bank,
                target_account_id,
                amount,
                timestamp,
                description=f"{kind} for {to_id}",
                entry_ids=self._new_entry_pair(),
                transaction_id=txn_id,
            )
            # The caller (_maybe_pay_income) already checked the source
            # account covers the FULL payday amount before calling any leg,
            # and the three legs' amounts sum to exactly that full amount
            # (by construction -- see _maybe_pay_income) -- so a per-leg
            # failure here would indicate a real bug, not a legitimate
            # runtime outcome, hence an assertion rather than a handled
            # branch.
            assert ok, f"leg-level post_transfer failed for {kind}/{to_id} despite a pre-checked source balance"
        else:
            target_bank.fund_external(
                target_account_id,
                amount,
                timestamp,
                description=f"{kind} for {to_id}",
                entry_ids=self._new_entry_pair(),
                transaction_id=txn_id,
            )
        self._record(
            transaction_id=txn_id,
            kind=kind,
            timestamp=timestamp,
            from_id=from_id,
            to_id=to_id,
            amount=amount,
            balance_before=balance_before,
            event_type=event_type,
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

        # Device: the payer's own device, or their household's shared
        # device if that's who they transact from -- self.person_device
        # already resolves to whichever one this person actually uses (see
        # the device-assignment pass in _build_world). A purchase attempt
        # is the one place in this simulation a person genuinely "uses a
        # device" -- see world/models.py's Transaction docstring for why
        # every other Transaction kind leaves device_id blank. Resolved
        # here, before the transfer is attempted, purely so the
        # device-blocked check immediately below can run before any money
        # actually moves -- this dict lookup draws no randomness, so
        # moving it earlier cannot perturb the RNG-draw sequence a normal
        # run already depends on.
        device_id = self.person_device[person.person_id]

        # Live-Risk-loop support (new -- see block_device()'s own
        # docstring and engine.py's "Live-loop support" section below):
        # ONE surgical, clearly-commented conditional, and the ONLY place
        # existing purchase logic is touched by this addition. This is a
        # PROVABLE no-op on a normal run(): self.blocked_devices is only
        # ever populated by an explicit block_device() call (see its own
        # docstring), which nothing in _build_world()/run()/_run_one_day()
        # ever makes (confirmed by grep) -- so on a normal run this `if`
        # is always False and every line below it (the ordinary post_
        # transfer/_record path) executes exactly as it did before this
        # addition, byte-for-byte. Only an external, opt-in orchestrator
        # (financial_system/bridges/live_risk_loop.py) ever calls
        # block_device(), and only after evaluating a REAL Heimdall Risk
        # verdict -- see that module's own docstring.
        #
        # When it DOES fire (live-Risk-loop mode only): the purchase is
        # mechanically prevented -- post_transfer() is never even called,
        # so no money moves and no ledger entry is posted -- and recorded
        # as a real payment_failure, reusing the SAME Transaction kind an
        # ordinary insufficient-funds failure uses (Heimdall's own real
        # FAILURE_TAXONOMY, financial_system/recovery/signals.py, already
        # names a `risk_block` category for exactly this situation -- a
        # payment failing because Risk blocked it, not because the payer's
        # balance was short), distinguished honestly via the Event's own
        # `payload` JSON (`blocked_device: true`, following the
        # `retried_from` precedent below -- see `_record()`'s own comment
        # for exactly why this is not a new required Transaction field)
        # and a distinct `event_type` (`purchase_blocked_device`, not
        # `purchase_failed`).
        if device_id in self.blocked_devices:
            timestamp = self._event_timestamp()
            balance_before = bank.balance_of(account_id)
            txn_id = self.ids.next_txn_id()
            self._record(
                transaction_id=txn_id,
                kind="payment_failure",
                timestamp=timestamp,
                from_id=person.person_id,
                to_id=merchant.merchant_id,
                amount=amount,
                balance_before=balance_before,
                event_type="purchase_blocked_device",
                device_id=device_id,
                blocked_device=True,
            )
            return

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
                device_id=device_id,
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
                device_id=device_id,
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
        device_id: str = "",
        retried_from: str = "",
        blocked_device: bool = False,
    ) -> None:
        # Phase 2: transaction_id is now generated by the caller (before
        # this is invoked), not here -- callers need the id up front to
        # pass as the `transaction_id` on the balanced ledger-entry pair
        # they post via world/agents/bank.py's primitives, so every
        # LedgerEntry can be traced back to the Transaction row that
        # caused it.
        #
        # device_id defaults to "" -- only _maybe_attempt_purchase passes a
        # real one (see world/models.py's Transaction docstring for why
        # every other kind is device-less).
        #
        # retried_from (new -- see attempt_retry() below and docs/Memory.md's
        # entry for it) defaults to "" and is deliberately NOT threaded onto
        # the Transaction dataclass itself, unlike device_id: Transaction rows
        # are written via `dataclasses.asdict()` against a FIXED fieldnames
        # list in run_simulation.py's write_output, so any new
        # always-present dataclass field would add a new CSV column to
        # EVERY transactions.csv row, on every run, breaking this task's own
        # "byte-identical to before this task" requirement for a normal
        # (non-live-loop) run. Carrying it in the Event's own `payload` JSON
        # instead (below) uses the exact mechanism docs/Design.md's "Output
        # format" section already names for this ("JSON only where a
        # record's shape is genuinely nested") and costs zero bytes on every
        # row where it doesn't apply -- the key is only ever added to the
        # dict when a caller actually passes retried_from (only
        # attempt_retry() does).
        #
        # blocked_device (new -- see block_device() and _maybe_attempt_
        # purchase()'s own device-blocked check above for why) follows the
        # EXACT same discipline: defaults to False, never touches the
        # Transaction dataclass, only ever added to the Event's own
        # `payload` JSON when a caller actually passes blocked_device=True
        # (only _maybe_attempt_purchase()'s device-blocked branch does).
        txn = Transaction(
            transaction_id=transaction_id,
            timestamp=timestamp,
            day=self.clock.day,
            from_id=from_id,
            to_id=to_id,
            amount=amount,
            kind=kind,
            balance_before=balance_before,
            device_id=device_id,
        )
        self.transactions.append(txn)

        # json.dumps with sort_keys=True keeps payloads byte-identical
        # across runs with the same seed (dict key order would otherwise
        # be an unnecessary source of nondeterminism-looking diffs).
        payload_fields = {
            "transaction_id": txn.transaction_id,
            "amount": amount,
            "from_id": from_id,
            "to_id": to_id,
            "balance_before": balance_before,
        }
        if retried_from:
            payload_fields["retried_from"] = retried_from
        if blocked_device:
            payload_fields["blocked_device"] = True
        payload = json.dumps(payload_fields, sort_keys=True)
        self.events.append(
            Event(
                event_id=self.ids.next_event_id(),
                event_type=event_type,
                subject_id=from_id,
                occurred_at=timestamp,
                payload=payload,
            )
        )

    # ------------------------------------------------------------------
    # Live-loop support -- ADDITIVE, OPT-IN methods only. Nothing in run()/
    # _run_one_day()/any other existing engine method calls any of the four
    # methods below (confirmed by grep -- see docs/Memory.md's entries for
    # these additions); a normal `run()` / `run_simulation.py` invocation's
    # control flow and RNG-draw sequence are completely unaffected by their
    # existence. They exist so an external, opt-in orchestrator can step
    # this engine day-by-day and write a real action back into it:
    #
    # - financial_system/bridges/live_recovery_loop.py (first built) takes
    #   a real mid-run snapshot and attempts a real, causally-determined
    #   retry of a specific earlier failed purchase -- see NORTH_STAR.md
    #   Working Section 23 ("Insufficient funds -> WAIT 24 HOURS ->
    #   RE-EVALUATE WORLD -> IF liquidity recovered -> retry"), driven by
    #   Heimdall's real recovery_agent.run_recovery_for_payment() decision
    #   instead of a hardcoded rule. Uses run_one_tick()/snapshot()/
    #   attempt_retry().
    # - financial_system/bridges/live_risk_loop.py (later, separate task)
    #   scores newly-active shared devices with Heimdall's real
    #   risk_agent.run_risk_for_device() and, on a real REVIEW/HOLD
    #   verdict, blocks that device for all future purchase attempts --
    #   see block_device()'s own docstring and _maybe_attempt_purchase()'s
    #   device-blocked check above. Uses run_one_tick()/snapshot()/
    #   block_device().
    #
    # Both orchestrators live outside Simulation/ because they inherently
    # straddle both systems, per this project's own design constraints.
    # ------------------------------------------------------------------

    def run_one_tick(self) -> None:
        """
        ADDITIVE, public wrapper around exactly one iteration of run()'s own
        loop body (`_run_one_day()` then `self.clock.advance()`) -- runs
        one more simulated day, with IDENTICAL effect to one iteration of a
        normal `run()` call. Exists purely so an external driver can step
        this engine day-by-day without calling underscore-prefixed
        "private" methods directly or re-implementing run()'s loop itself.
        `run()` is unchanged -- it still calls `_run_one_day()`/
        `self.clock.advance()` directly, not through this method.
        """
        self._run_one_day()
        self.clock.advance()

    def snapshot(self) -> SimulationResult:
        """
        ADDITIVE: builds a `SimulationResult` from this engine's CURRENT
        state, at any point during a live (not-yet-finished) run -- not
        just at the very end of a full `run()` call. Field-for-field
        identical construction to what `run()` does at its own end (see
        `run()` above); read-only, mutates nothing. Used by the external
        live orchestrator to write a real CSV snapshot of the world exactly
        as it stands right now (including any retry transactions attempted
        so far) for the Heimdall bridge to ingest.
        """
        accounts = [acct for bank in self.banks for acct in bank.accounts.values()]
        return SimulationResult(
            persons=self.persons,
            banks=self.banks,
            merchants=self.merchants,
            households=self.households,
            organizations=self.organizations,
            communities=self.communities,
            devices=self.devices,
            accounts=accounts,
            transactions=self.transactions,
            events=self.events,
            seed=self.seed,
            num_days=self.num_days,
        )

    def attempt_retry(
        self,
        original_transaction_id: str,
        person_id: str,
        merchant_id: str,
        amount: float,
        day: int | None = None,
    ) -> bool:
        """
        ADDITIVE, dead code from run()'s own perspective (see this class's
        "Live-loop support" section docstring above) -- attempts a REAL
        retry of a specific, already-failed purchase: the SAME person, SAME
        merchant, SAME amount as the original failed transaction
        (`original_transaction_id`) -- a retry retries the SAME purchase,
        it does not invent a new one. Uses the exact same
        `post_transfer()` + `_record()` machinery `_maybe_attempt_purchase`
        already uses for an ordinary purchase, so success or failure is
        decided by the person's REAL, CURRENT balance at the moment this is
        called -- never a scripted or forced outcome (NORTH_STAR.md's own
        rule, Working Section "But Simulation Must Never Become Fake
        Truth": "no magical outcomes"). If the balance still can't cover
        the amount, this honestly fails again, exactly like a real second
        attempt would.

        `day` is accepted only for the CALLER's own bookkeeping/assertions
        (e.g. "did I actually schedule this for the day I intended") -- this
        method itself does not read or depend on it; the simulated day this
        transaction is recorded on is always whatever day
        `self.clock.current_date`/`self.clock.day` actually is right now.

        Records the outcome as a NEW Transaction (never a mutation of the
        original failed one, which is left exactly as it was recorded),
        `kind="retry_success"` or `"retry_failure"` -- two new values added
        to Transaction's `kind` vocabulary for this task (see
        docs/Design.md's "Naming conventions" section and docs/Memory.md's
        entry for this method). The link back to the original failed
        attempt is carried in the corresponding Event's `payload` JSON
        (`retried_from` key), not as a new Transaction field/CSV column --
        see `_record()`'s own comment above for exactly why.

        Determinism: draws from this engine's single seeded `self.rng` in
        exactly the same fixed position every other transaction-producing
        call draws from (`_event_timestamp()`, inside `_record`'s caller
        path here just like `_maybe_attempt_purchase`) -- `post_transfer`
        and `_new_entry_pair` draw no randomness at all. The EXTERNAL
        orchestrator is responsible for calling this method in a fixed,
        reproducible order across scheduled retries on the same simulated
        day (sorted by `original_transaction_id`, never dict/set iteration
        order) -- see live_recovery_loop.py's own determinism section for
        the full guarantee.
        """
        account_id = self.person_account[person_id]
        bank = self._account_bank[account_id]
        merchant_pending_account_id = self.merchant_pending_account[merchant_id]
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
            description=f"retry of {original_transaction_id} at {merchant_id}",
            entry_ids=self._new_entry_pair(),
            transaction_id=txn_id,
        )
        device_id = self.person_device[person_id]

        self._record(
            transaction_id=txn_id,
            kind="retry_success" if succeeded else "retry_failure",
            timestamp=timestamp,
            from_id=person_id,
            to_id=merchant_id,
            amount=amount,
            balance_before=balance_before,
            event_type="retry_succeeded" if succeeded else "retry_failed",
            device_id=device_id,
            retried_from=original_transaction_id,
        )
        return succeeded

    def block_device(self, device_id: str, day: int | None = None) -> None:
        """
        ADDITIVE, dead code from run()'s own perspective (see this class's
        "Live-loop support" section docstring above) -- marks `device_id`
        BLOCKED: a REAL state change, consulted by `_maybe_attempt_
        purchase()`'s own device-blocked check (see that method's own
        comment for exactly where and how). Once blocked, EVERY future
        purchase attempt from a person whose resolved device
        (`self.person_device[person_id]`) is this `device_id` mechanically
        fails -- `post_transfer()` is never even called for it, so no
        money moves -- recorded as a `payment_failure` with a distinct,
        honest `event_type`/payload marker (see `_maybe_attempt_
        purchase()`'s comment). This is a REAL mechanical consequence, not
        a cosmetic "would have blocked" log entry: `test_live_risk_loop.py`
        proves it against real, traced purchase attempts, not just this
        method's own state.

        Idempotent on `self.blocked_devices` (a set -- blocking an
        already-blocked device changes nothing there), though a new
        `device_blocked` Event is still appended every call, honestly
        recording every real decision that led to (or reaffirmed) this
        device's blocked state. The external orchestrator
        (financial_system/bridges/live_risk_loop.py) tracks which devices
        it has already blocked itself and only calls this once per device
        (see that module's own report) -- this method does not enforce
        that on its own.

        `day` is accepted only for the CALLER's own bookkeeping/assertions
        -- exactly like `attempt_retry()`'s own `day` parameter above --
        this method itself does not read or depend on it; the simulated
        day this block is recorded on is always whatever day
        `self.clock.day` actually is right now. `live_risk_loop.py` always
        calls this AFTER that day's own `run_one_tick()` (the day's Risk
        checkpoint runs once that day's real transaction stream is known),
        so a block always takes effect starting the NEXT simulated day's
        purchases -- never retroactively, and never against the very
        attempts whose activity caused the REVIEW verdict in the first
        place (NORTH_STAR.md's "no magical outcomes" rule, same spirit as
        `attempt_retry()`'s own real-balance-at-a-later-point design).

        Determinism: draws NO randomness at all -- unlike `attempt_retry()`'s
        own `_event_timestamp()` call, the `device_blocked` Event below
        uses a FIXED canonical timestamp (`self.clock.timestamp(hour=0,
        minute=0, second=0)`), deliberately: a device block is a Risk-
        system decision landing on a simulated day, not a person's own
        randomly-timed activity, so it has no reason to consume
        `self.rng`. This means `block_device()` can be called any number
        of times, in any order, without perturbing `self.rng`'s own
        draw sequence at all -- the ONLY thing that can ever perturb it is
        the `_event_timestamp()` draws inside a device-blocked purchase
        failure itself (`_maybe_attempt_purchase()`), which happen in the
        SAME fixed per-person iteration order `_run_one_day()` already
        uses for everything else (see that method's own docstring) --
        never introduced by this method.
        """
        self.blocked_devices.add(device_id)
        self.events.append(
            Event(
                event_id=self.ids.next_event_id(),
                event_type="device_blocked",
                subject_id=device_id,
                occurred_at=self.clock.timestamp(hour=0, minute=0, second=0),
                payload=json.dumps({"device_id": device_id, "day": self.clock.day}, sort_keys=True),
            )
        )
