# Phases — Financial World Simulation

The long-term vision behind this project (agent-based institutions,
research-driven world-building, AML/credit/treasury domains, a
Discovery.AI-powered research-to-world pipeline) is real and worth
recording — but it is not one phase, it's many, and building them out
of order or all at once has already been tried, in conversation, and
correctly rejected as unrealistic. This file exists specifically so
that doesn't happen by accident: only Phase 1 is currently authorized.
Everything past it is direction, not a commitment.

## Phase 1 — Minimal agent-based world core (ACTIVE)

Build exactly what `PRD.md` and `Architecture.md` describe: Person,
Bank, Merchant agents; a tick-based clock; simple documented
probability rules; a real event-log output; basic descriptive
statistics; determinism given a seed. Nothing else.

**Done means**: the simulation runs end-to-end, produces a real
event log, every rule's provenance is stated, tests pass (determinism,
no negative balances, well-formed output), and there's an honest
written report of what the output actually looks like — including if
it turns out to be no more useful than expected.

## Phase 2 — Institutional depth (DONE)

Built: a real double-entry ledger for Bank (`LedgerEntry.entry_type`
debit/credit, unsigned magnitude, `transaction_id`-linked pairs;
`world/agents/bank.py`'s `fund_external`/`post_transfer` post every
economic movement as a balanced pair against the right side of the
balance sheet -- a new `bank_reserve` asset account per Bank represents
external inflows, customer/merchant accounts are liabilities); the
existing per-Bank Account registry, extended with a second
`merchant_pending` account per Merchant; and basic settlement (purchase
proceeds land in a Merchant's pending account, then move to their
settled/spendable account on a fixed T+1 sweep, `world/engine.py`'s
`_run_settlement`). Global double-entry invariant (debits == credits
across the whole ledger, always) and no-negative-balance are both
tested, including for the two new account types. 24 tests passing (9
original Phase 1 + 15 new, `tests/test_ledger.py`). See
`Simulation/docs/Memory.md`'s "Phase 2" section for full detail,
provenance of the new settlement-timing rule, and honest caveats
(notably: cross-bank transfers don't model real interbank settlement
mechanics, and opening balances remain outside the ledger's scope,
exactly as in Phase 1).

## Phase 2.5 — Institutional & social abstractions (DONE)

Built: two *structural* abstractions layered over the existing Person/
Bank/Merchant agents, per Architecture.md's guiding principle that only
Person/Bank/Merchant carry probabilistic decision logic — nothing built
here is a new decision-maker. (A) A second, savings Bank account per
Person (`owner_type="person_savings"`), with a fixed fraction of every
salary payment swept into it (`world/engine.py`'s `SAVINGS_SWEEP_
FRACTION`); purchases still only ever draw from checking. (B) Three new
dataclasses in `world/models.py`: `Household` (groups Persons, a further
fixed fraction of salary sweeps into a shared account —
`HOUSEHOLD_SWEEP_FRACTION`), `Organization` (groups Persons as employees,
gives the group a real, ledger-backed revenue account — an
Organization-employed person's salary is a genuine `post_transfer` from
that account, not the synthetic `employer:<id>` convention, so payroll
can, in principle, fail if underfunded — it did not in this session's
example run, by generous design, not by structural prevention), and
`Community` (a deliberately inert grouping of Households/Organizations,
with NO money-movement mechanic at all, per the project owner's own
explicit framing that this abstraction should exist for possible future
use without inventing a reason for it now). Also built: a standalone
`validation/` package (Part B of this task) that samples a completed
run's output and reports two clearly separate things — B.1 internal
mechanism consistency (double-entry invariant, no negative balances, the
causal balance/failure-rate check, savings/household accumulation
accuracy, organization payroll traceability) and B.2 comparison against
`docs/Research.md`'s cited real-world numbers (income distribution shape,
spend/income ratio by income level, settlement timing — with fraud/
credit/loans explicitly reported NOT APPLICABLE, since they remain
design-only per Research.md Part C). The validation system's B.2 check
correctly detected and reported, from real simulation output, the exact
gap Research.md's own prose already predicted: this simulation's
purchase-amount mechanic does NOT reproduce the real-world pattern of
poorer people spending a larger income share (bottom-income-quartile vs.
top-income-quartile spend/income ratio differed by only ~1% relatively in
a 500-person/120-day run, well under the 15% threshold that would
indicate the real pattern). 45 tests passing (24 from Phase 1/2 + 21 new
— `tests/test_phase25.py` and `tests/test_validation.py`). See
`Simulation/docs/Memory.md`'s "Phase 2.5" section for full design
rationale, every new constant's provenance, and honest caveats (notably:
Household's size distribution is an uncited, honestly-labeled guess, and
Organization revenue funding is a one-time world-generation-time lump sum
rather than a periodic stream).

## Device — real device identity + household sharing (DONE, 2026-09-04)

Built, outside the numbered Phase sequence (a follow-on task, not part of
Phase 3+): a real `Device` entity (`world/models.py`), replacing the
Heimdall bridge's previous one-fabricated-placeholder-per-person device.
Every Person is linked to exactly one Device at world-generation time
(`world/engine.py`, a new pass run right after Household grouping). The
ONE legitimate sharing mechanism modeled: for each household with 2+
members, its first member is the "primary" device holder, and each other
member independently has a 30% chance (`DEVICE_HOUSEHOLD_SHARING_
FRACTION`, a named MODELING ASSUMPTION) of sharing that same device
instead of getting their own. No fraud-ring or cross-household sharing
mechanism was added — explicitly out of scope, per `docs/Research.md`
Part C.1 and this task's own instructions. Every purchase/payment_failure
Transaction now carries the payer's real `device_id`; `run_simulation.py`
writes a new `devices.csv`. 53 tests passing (45 prior + 8 new,
`tests/test_device.py`). See `docs/Memory.md`'s "Device" section for full
design rationale, provenance, and the Heimdall-bridge motivation.

## Phase 3 — Behavioral realism (NOT STARTED)

Replace Phase 1's placeholder/assumption-labeled probability rules
with research-grounded ones where real sources exist (income
distributions, spending patterns) — each swap cited, not assumed.

(A separate, later task called itself "Truman Phase 3: the Mechanism
Engine" and added a pluggable failure-mechanism framework plus one new,
research-grounded failure cause — see the unnumbered "Mechanism Engine"
entry below. It does NOT satisfy this Phase 3's actual scope above
(no existing probability rule was swapped for a cited one); this line
stays NOT STARTED deliberately, per that entry's own honest framing.)

## Mechanism Engine — pluggable failure-cause framework + ExpiredInstrument (DONE (one slice), 2026-09-04)

Built, outside the numbered Phase sequence (a follow-on task, like Device
above, not a claim of full Phase 3 or Phase 4 completion): a real,
pluggable `FailureMechanism` framework (`world/mechanisms.py`) replacing
the single inline balance check `_maybe_attempt_purchase()` used to have,
plus ONE new, causally-real mechanism on top of it —
`ExpiredInstrumentMechanism`, which fails a purchase attempt if the
payer's `Device` (`world/models.py`) is past its own research-grounded
validity window (`DEVICE_VALIDITY_PERIOD_DAYS_RANGE`, `world/engine.py`),
regardless of balance. The framework refactor itself was proven behavior-
neutral (byte-identical output for the same seed/config, before vs. after,
`diff -rq` clean) before the new mechanism was added; adding the new
mechanism deliberately DOES change simulation output (new failure
category, different transaction counts), as expected and reported
honestly. 70 tests passing (56 prior + 14 new, `tests/test_mechanisms.py`),
one existing test (`test_engine.py::test_payment_failure_never_moves_
money`) deliberately updated with a stated reason (its old blanket
`balance_before < amount` assertion is no longer true for every
`payment_failure`, now that a second, balance-independent cause exists).
This is a genuine slice of BOTH Phase 3's spirit (one new research-
grounded constant, `DEVICE_VALIDITY_PERIOD_DAYS_RANGE`) and Phase 4's
spirit (a new mechanism generated causally from agent state — a Device's
own age — not a fresh coin flip) without completing either phase's full
originally-scoped work. See `docs/Memory.md`'s "Phase 3" section for full
design rationale, provenance, real numbers, and honest caveats (notably:
this is the SECOND of Heimdall's seven real failure categories Truman's
own mechanism now exercises, `expired`, alongside the pre-existing
`insufficient_funds` — five remain unmodeled, per `docs/Memory.md`'s own
list).

## Phase 4 — Domain events (NOT STARTED)

Payment retries, refunds — generated causally from agent state
(insufficient balance → later retry once income lands), the specific
capability gap Heimdall's own audits found the current dataset
couldn't support.

## Phase 5 — Scale and performance (NOT STARTED)

Larger populations, longer time spans, performance work if the Phase
1-4 design doesn't scale naturally.

## Phase 6 — Heimdall bridge (NOT STARTED, NOT ASSUMED)

Whether and how this simulation's output ever feeds into
`financial_system/` is an explicit decision to make later, with the
user, once there's something real to evaluate — not a default outcome
of this project existing.

## Beyond Phase 6 (VISION ONLY, NOT SCHEDULED)

The larger roadmap from the conversation this project grew out of —
AML, credit risk, chargeback/refund lifecycles, treasury, markets,
full institutional registries, a research-ingestion pipeline that
turns papers into world mechanisms, counterfactual/adversarial world
generation, a three-graph (world/knowledge/evidence) architecture,
eventual model training on simulated worlds — is recorded here as
long-term direction, not as a task list to work through. Each of
these is independently a Phase-1-sized undertaking in its own right.
Revisit this list only after Phase 1 has produced something real
enough to justify the next concrete step, and scope that step the
same way Phase 1 was scoped: small, bounded, honestly evaluated
before moving on.
