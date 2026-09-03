# Simulation Architecture Specification for Heimdall

This document is a research-and-design deliverable, not a build plan. It
follows the same discipline as `docs/NORTH_STAR.md` and
`docs/FUTURE_ARCHITECTURE.md`: it distinguishes, at every claim, between
**what already exists and is tested** (cited to an exact file),
**what is a real, sourced empirical fact** (cited to a real publication —
reusing `Simulation/docs/Research.md`'s own citations where applicable,
never re-deriving them from scratch), and **what is a design proposal or
architectural opinion** (labeled as such, not dressed up as either of the
first two). Nothing here should be read as implemented unless it names a
specific file and line of behavior that a reader could go check.

Two things distinguish this document from `NORTH_STAR.md`. First, its
subject — the simulation/world-modeling pipeline — is not purely
aspirational here the way most of `NORTH_STAR.md` is: `Simulation/` is a
real, running, tested codebase (45 passing tests as of this writing,
`Simulation/docs/Memory.md`), and a working *instance* of a meaningful
fraction of what this document specifies already exists. Second, this
document was produced by working through a long, deliberately
progressive research prompt (reproduced in the task that generated it)
section by section — Part I below preserves that structure and that
depth, arriving at conclusions rather than asserting them; Part II
distills those conclusions into the actual specification the prompt's
own final section asks for.

**Scope discipline, stated up front and held throughout**: this is a
long-term vision document, exactly like `NORTH_STAR.md`. It is not a plan
for the remaining hours of any buildathon submission window. Section 32
(Part I) and the "BUILD NOW" classifications throughout are deliberately
short lists — the temptation this document resists, explicitly, is
recommending its own comprehensive implementation.

---

# PART I — Progressive Research

## Working Section 1 — What Are We Actually Trying to Simulate?

The reflex answer — "transactions" — is wrong, and the research prompt is
right to rule it out first. A transaction is a *record*: one row saying
money moved from A to B. It has no memory of why, no connection to what
happens next, and no relationship to any other row except by coincidence
of shared fields. `Simulation/docs/PRD.md`'s own "Why" section names the
concrete failure mode this produces: `financial_system/data_generator/`'s
`retry_would_succeed` is "a category-level coin flip with zero connection
to customer, amount, timing, or history" — confirmed by reading that
generator's own source, not asserted. A dataset generated that way cannot
support any capability that depends on *why* something happened, because
nothing in its generation process encoded a why.

So what are we simulating? Not "transactions," and not any single item
from the research prompt's list in isolation either (people, banks,
markets...) — the minimum coherent unit is all of the following, together,
because none of them is meaningful without the others:

- **Entities** that persist and have state (a person has a balance
  *tomorrow* that depends on what happened *today*).
- **Relationships** between entities (a person has *an* account at *a*
  bank; a merchant is paid *by* customers *through* a bank).
- **Constraints** that entities cannot violate (a person cannot spend
  money they do not have — `Simulation/docs/Rules.md` #7).
- **Mechanisms** that connect entity state to entity behavior (a
  person's spend probability is a function of their own balance —
  `Simulation/world/agents/person.py`'s `spend_probability`).
- **Time**, as the axis along which state evolves and events are ordered,
  not just a timestamp column.

**Minimum conceptual definition of a financial world**: a financial world
is a set of entities with persistent state, connected by relationships and
constraints, whose state changes only through discrete events, where the
probability or occurrence of each event is a function of the state of the
entities involved (not of a global, entity-independent distribution). A
transaction log is one *observable projection* of that world — specifically,
the record of which events occurred — not the world itself. This is the
document's central, load-bearing distinction, restated by the research
prompt itself as the "Core Principle" and worth stating in first-principles
form here: **you cannot recover a world from its projection**, but you can
generate an unlimited number of consistent projections from a world, and
every one of them will share the world's actual causal structure. That
causal structure — not volume, not superficial realism — is the entire
reason to build a world instead of a generator.

### Synthetic Dataset Generator vs. Agent-Based Financial World Simulator

| | Synthetic Dataset Generator | Agent-Based Financial World Simulator |
|---|---|---|
| Unit of design | A row schema + a set of independent field distributions | A set of entities, each with its own state and decision function |
| Where "why" lives | Nowhere — a label is chosen, then row content is generated to match it | In the entity's own state at the moment of the event |
| Correlation across rows | Only what's explicitly hand-coded (e.g. "10% of failures happen to be near month-end") | Emerges from shared entities across rows (the same person's balance links their salary row to their next purchase row) |
| Can it produce a causal chain like "income shock → liquidity reduction → missed repayment"? | Only if that specific chain is manually authored as a rule | Yes, if the constituent single-step mechanisms are each present, because the chain is just those mechanisms composing over time |
| Failure mode when wrong | Silently produces implausible correlations no one can find without auditing every rule by hand | Produces an inspectable, traceable wrong number you can attribute to one constant (`Simulation/docs/Memory.md`'s "Open questions" section does exactly this for its own transition-point finding) |
| Cost/complexity | Lower to build initially | Higher to build initially, much lower to *extend* correctly (a new mechanism composes with existing ones instead of needing its own bespoke correlation rules) |

**[ALREADY BUILT]** `Simulation/` is a working instance of the right-hand
column, already proven to produce the specific causal chain the research
prompt names as an example (income shock → liquidity reduction → missed
payment), documented with real numbers in
`Simulation/docs/Memory.md`'s "The actual research finding" section: failure
rate falls monotonically from 96.25% to 0.00% as an agent's own
balance-to-income ratio rises, verified across three separate seeds. This
is not a design goal stated on paper — it is a measured property of
25,000+ real generated transactions, and the document treats it as the
single strongest piece of existing evidence that the "world, not generator"
distinction is not merely conceptually cleaner but practically consequential.

## Working Section 2 — World Ontology

Separating the research prompt's eight categories against what a
financial world actually needs:

- **ENTITY** — a thing with identity and persistent state across time
  (Person, Bank, Merchant, Household, Organization — all four already
  exist as dataclasses, `Simulation/world/models.py`).
- **EVENT** — a discrete, timestamped occurrence that changes state
  (`Simulation/world/models.py`'s `Event`, append-only, mirroring
  Heimdall's event-sourcing discipline per that file's own docstring).
- **STATE** — the entity's current condition, itself a function of its
  event history (`Account.balance`, reconstructable "always exactly the
  sum of its ledger's credit amounts minus its debit amounts... replayed
  from zero" per `Simulation/world/agents/bank.py`'s module docstring).
- **RELATIONSHIP** — a durable link between entities (`Household.person_ids`,
  `Organization.employee_person_ids`, an `Account.owner_id` pointing back
  to its Person/Merchant/Bank — all in `Simulation/world/models.py`).
- **CONTRACT** — a durable, bilateral commitment with obligations attached
  to both sides (a loan, an insurance policy, an employment agreement).
  **[NOT BUILT]** — nothing in `Simulation/` today is a Contract in this
  sense; `Organization.employee_person_ids` is a *membership* relationship,
  not a Contract with terms, and the synthetic `employer:<person_id>`
  salary source (`Simulation/world/engine.py`) is explicitly not a modeled
  agent at all, let alone a contract with one.
- **OBLIGATION** — a single, resolvable instance of a contract coming due
  (an installment, a premium payment). **[NOT BUILT]**, same reason.
- **RESOURCE** — a fungible or non-fungible thing of value an entity can
  hold (money, in every account balance today; nothing beyond money yet).
- **POLICY** — a rule an institution applies to its own decisions, capable
  of changing (a bank's lending criteria, a merchant's refund policy).
  **[NOT BUILT]** — `Simulation/`'s institutions (Bank, Merchant,
  Organization) have fixed mechanical behavior, not a Policy object they
  consult and that could itself be varied as an experimental parameter.
- **MECHANISM** — the causal rule connecting state to event probability or
  event to state change (`Person.spend_probability`,
  `Bank._post`'s double-entry posting rule — both built,
  `Simulation/world/agents/person.py` and `bank.py`).

**Why each abstraction is necessary, not just listable**: ENTITY and STATE
exist so that "what is true right now" is a well-defined question with one
answer. EVENT exists so that "what changed, and when" is auditable — this
is what makes the causal chains in Working Section 6 traceable rather than
merely plausible-looking. RELATIONSHIP exists so events can propagate
across entities (a Person's own purchase affects a Merchant's own pending
balance — this is *the* mechanism `Simulation/world/engine.py`'s
`_maybe_attempt_purchase` implements). CONTRACT and OBLIGATION are the two
genuinely missing abstractions with the highest leverage: essentially
every "beyond Phase 2.5" domain named in `NORTH_STAR.md` §27
(Credit, Insurance, Settlement obligations, even Payments' own
authorization-then-capture two-step) is a Contract/Obligation pair the
current ontology has no vocabulary for — a Loan is a Contract, an
installment is an Obligation resolving against it. RESOURCE exists so
"what does this entity have" generalizes beyond money (inventory, credit
lines, collateral) without a new top-level concept per resource type.
POLICY exists specifically so institutional behavior can be an
*experimental variable* (Working Section 15's scenario axis "policies")
rather than a hardcoded constant a researcher has to edit source to vary.
MECHANISM is the connective tissue between STATE and EVENT and is where
every provenance label in Working Section 9's pipeline ultimately attaches.

**Universal vs. domain-scoped**: ENTITY, EVENT, STATE, RELATIONSHIP, and
the event-sourcing discipline that projects STATE from EVENT history are
universal — every domain (payments, credit, AML, insurance) needs them and
none should reinvent them, mirroring `NORTH_STAR.md` §6's "World Registry"
and §26's "Domain Package Architecture" almost exactly. CONTRACT and
OBLIGATION are universal *shapes* but domain-specific *content* — a Loan
contract and an InsurancePolicy contract share the shape (parties, terms,
a schedule of obligations, a status) but not the terms themselves, which
is why they belong to domain packages layered on a shared Contract base,
not as one undifferentiated Contract class. POLICY and MECHANISM are
domain-owned by construction (a bank's lending policy has nothing in
common with a merchant's pricing policy except that both are "a rule an
institution consults"), but the *registry and versioning discipline*
around them (Working Section 27's reproducibility model) is universal.

## Working Section 3 — State

For a Person (the richest agent Simulation currently models), splitting
state by kind:

| Kind | Example (Person) | Where it lives today |
|---|---|---|
| Persistent | `income_monthly`, `risk_preference`, `payday` | `Simulation/world/models.py` `Person` dataclass fields, fixed at world-generation time |
| Derived | `Account.balance` | Reconstructable by replaying `Account.ledger` from zero (`bank.py` module docstring) — **[ALREADY BUILT]**, and this is the crucial property: state is not stored truth, it is a *projection* of event history, exactly `State(t+1) = Transition(State(t), Event(t))` |
| Temporary | The RNG draw outcome for "does this person attempt a purchase today" | Not persisted anywhere — computed fresh each tick from `spend_probability`, consumed immediately |
| Historical | The full sequence of a person's own transactions | `transactions.csv` / `events.csv`, append-only, never mutated |
| Latent | A person's *true* underlying spending propensity distribution | Never observed directly — only realized outcomes (purchase attempts) are recorded; the generating distribution itself is simulator-internal ground truth (see Working Section 19) |
| Observable | Everything in `persons.csv`/`transactions.csv` at run end | Exactly what the simulator writes to output today — **[DESIGN GAP]**: today, "observable" = "the entire event log," i.e. simulator-internal ground truth and Heimdall-observable state are the same thing. Working Section 18 argues this needs to change. |

For a Bank (the richest institution today): persistent = none really (a
Bank agent has no config beyond `bank_id`/`name`); derived = every
account's balance, all reconstructable from `ledger`; historical = the
full `ledger_entries.csv`. A real bank (per `NORTH_STAR.md` §11's
"CUSTOMER SYSTEM / ... / RISK / FRAUD / AML / COMPLIANCE / POLICY") would
also need policy state (current lending criteria), risk-exposure state
(aggregate credit outstanding by risk tier), and liquidity state (reserve
ratio, funding costs) — **[NOT BUILT]**, and correctly out of scope per
`Simulation/docs/Phases.md`'s Phase 2/2.5 scope lines, which explicitly
built only "a real double-entry ledger... an Account registry, basic
settlement," not a Risk/Fraud/AML/Compliance system for the simulated Bank
itself.

**`State(t+1) = Transition(State(t), Event(t))`, concretely, and why it
differs from "modifying rows"**: `Simulation/world/agents/bank.py`'s
`_post()` is a literal, minimal instance of this equation — it never
overwrites a balance field arbitrarily; it always computes the new balance
as a function of the old balance plus a signed delta determined by the
event (`entry_type` + the account's side of the balance sheet), and it
*also* appends the event itself (`LedgerEntry`) to permanent history in
the same call. A row-modification approach (`UPDATE accounts SET balance =
5000 WHERE id = 'x'`) is a state assignment with no attached event — you
can no longer answer "why is it 5000" after the fact, because the
transition that produced it was never recorded as a first-class object.
Every invariant `Simulation/tests/test_ledger.py` checks (global
double-entry balance, per-transaction balance, "every LedgerEntry
resolves to a real Transaction") is a check that this equation held
everywhere, every time — which is only checkable at all because the
transition function's inputs and outputs were both preserved, not just
its output.

## Working Section 4 — Events

Applying the research prompt's per-event attribute list to one event
already implemented (`purchase_failed`, emitted from
`Simulation/world/engine.py`'s `_maybe_attempt_purchase`):

| Attribute | Value for `purchase_failed` |
|---|---|
| actor | the Person (`from_id`) |
| target | the Merchant (`to_id`) |
| timestamp | ISO 8601 UTC, derived from `SimClock` + a seeded RNG time-of-day draw (`_event_timestamp()`) |
| cause | `post_transfer()` observed `amount > from_account.balance` at the moment of the attempt |
| inputs | the attempted `amount` (from `Person.purchase_amount`), the account's current balance |
| state before | `balance_before` — a field this project added *beyond* `Simulation/docs/Architecture.md`'s minimal spec specifically so this could be checked, per `models.py`'s `Transaction` docstring |
| state after | unchanged (no money moved — `post_transfer` "returns False and posts NOTHING at all") |
| economic effect | none directly, but downstream: this is exactly the event `Simulation/docs/Research.md`'s Part C.2 proposes as the natural trigger for a future credit-score decrement |
| provenance | `event_type="purchase_failed"`, `kind="payment_failure"` — both explicit fields, not inferred |

Events not yet in the simulator but named in the research prompt's list
(`RefundIssued`, `ChargebackOpened`, `LoanIssued`, `InstallmentDue`) are
**[NOT BUILT]** — `Simulation/docs/Phases.md` Phase 4 ("Payment retries,
refunds — generated causally from agent state") is the closest authorized
future scope, explicitly not started.

**State-first or event-first?** Event-first, and `Simulation/` already
made this choice correctly, not by accident: `world/models.py`'s own
docstring states the project "mirrors Heimdall's event-sourcing
discipline," and `bank.py` proves it structurally — `Account.balance` is
described as "a live cache... the ledger is the source of truth," not the
reverse. The reasoning, generalized: a state-first world can answer "what
is true now" trivially but cannot answer "what was true then" or "why is
this true now" without a separate audit log bolted on after the fact — and
that bolted-on log is exactly what a state-first design tends to treat as
optional, which is how `financial_system/`'s original generator ended up
with rows that assert an outcome without encoding a cause. An event-first
world makes state a *derived, always-recomputable* view, so "what was true
at time t" (`NORTH_STAR.md` §5's temporal-snapshot requirement) is answered
by replaying events up to t, not by a separate mechanism that has to be
kept consistent with the "real" state by hand. This is also precisely
`NORTH_STAR.md` §4's "Systemic Change #2 — Make Events Universal" and its
principle "the current state is a projection of history" — already true
in miniature in `Simulation/`, proposed at full scale there.

## Working Section 5 — Agent Model

`Simulation/docs/Architecture.md`'s core data model already answers "what
is an agent," concretely, for three agent classes — not abstractly, as
code:

```
Agent
├── identity        person_id / bank_id / merchant_id
├── role            Person | Bank | Merchant (Phase 2.5: + Household,
│                   Organization -- structural, not decision-making, see
│                   below)
├── state           income_monthly, balance (via Account), risk_preference
├── objectives       [IMPLICIT, not modeled explicitly -- see below]
├── preferences      risk_preference (0=cautious..1=impulsive)
├── constraints      cannot spend below zero (Bank.post_transfer's
│                   balance check; Rules.md #7)
├── information       [IMPLICIT -- an agent's own state only; see below]
├── beliefs           [NOT MODELED -- see below]
├── policies          [NOT MODELED for Person; institutions have none yet]
├── available actions  receive income, attempt a purchase (Person);
│                    post a ledger entry, run settlement (Bank, Merchant)
└── behavioral model   explicit closed-form probability functions
                      (Person.spend_probability, Person.purchase_amount)
```

**Objectives, information, and beliefs are honestly absent, not hidden.**
`Simulation/`'s Person agent does not maximize anything — it has no
utility function, only a probability function tuned by hand
(`BASE_DAILY_SPEND_PROB`, `RISK_MULTIPLIER_MIN/MAX`, all labeled MODELING
ASSUMPTION in `person.py`). This is a real limitation worth naming
plainly: a true utility-maximizing agent would *choose* how much to spend
given its beliefs about future income and its risk preference; Phase 1's
Person instead has spend probability and spend amount as two independent,
hand-specified functions of state that happen to correlate the right way.
The observed causal chain (Working Section 1) is real, but it is a
property of the *mechanism's construction*, not evidence of emergent
utility-maximizing behavior — an honesty distinction worth holding onto
for Working Sections 6 and 22.

**Which behaviors suit which approach, mapped against what's actually
built and what plausibly comes next:**

| Approach | Suited for | Status |
|---|---|---|
| Rules (deterministic) | Constraints that must never be violated (no negative balance), fixed institutional procedures (T+1 settlement sweep) | **[BUILT]** — `post_transfer`'s balance check, `_run_settlement`'s fixed schedule |
| Probability distributions | Independent per-agent traits at world-generation time (income level, risk preference) | **[BUILT]** — log-normal income, uniform risk_preference, both in `engine.py` |
| Conditional probability functions, `P(action \| state)` | Day-to-day behavioral decisions whose likelihood should visibly depend on the agent's own state | **[BUILT]** — `spend_probability(balance)`; this is the actual mechanism behind Working Section 1's causal chain |
| Markov processes | State that transitions through a small number of named regimes with path-dependent probabilities (e.g. a credit-score band, a "compromised account" flag) | **[PROPOSED]** — `Research.md` Part C.1's "compromise event" (once compromised, stays compromised until resolved) and Part C.2's credit-score band transitions are both naturally Markov-shaped; neither is built |
| Utility functions / decision theory | An agent that must trade off among several distinct actions, not just decide yes/no on one | **[PROPOSED, none justified yet]** — Phase 1's Person only ever considers one action (attempt today's purchase); a genuine utility-maximizing choice (spend vs. save vs. invest) isn't needed until an agent has more than one real option |
| Game theory | Strategic interaction where one agent's optimal action depends on another agent's *anticipated* action (a fraudster reacting to a bank's detection threshold) | **[PROPOSED]** — the natural fit for Working Section 26's adversarial worlds; nothing today requires it because no agent currently reasons about another agent's policy |
| Network models | Behavior that depends on an agent's position in a relationship graph, not just its own state | **[PARTIALLY BUILT, inert]** — `Household`/`Organization`/`Community` are real relationship structures (`Simulation/world/models.py`), but per that file's own docstrings none of them currently *influence* any agent's decision function; they are grouping/account structures only |
| Machine-learned policies | Behavior too complex or too poorly understood mechanistically to hand-specify, learned from either real data or from playing the simulator itself | **[NOT JUSTIFIED YET]** — see Working Section 24; nothing in this codebase has hit the ceiling of hand-specifiable rules yet, and per `Simulation/docs/Rules.md` #1, an ML policy replacing a hand-specified one would need the same auditability bar a hand-specified rule already clears trivially |

**[DESIGN OPINION]** LLMs specifically are absent from this table on
purpose, for the same reason `Simulation/docs/Rules.md` #1 states plainly:
"Agent decisions... must come from explicit, readable probability
functions — not a model call... the simulation needs to be fast,
deterministic-given-a-seed, and auditable." Nothing in the research prompt's
list of suitable techniques needs an LLM, and every technique in the table
above is strictly more inspectable than an LLM call would be for the same
decision. This isn't a claim that LLMs can never belong near agent
behavior — Working Section 24 revisits machine-learned policies as a real,
if currently unjustified, future option — only that none of today's or the
near-term's behaviors clear the bar for needing one.

## Working Section 6 — Behavioral Generation

`Simulation/world/agents/person.py`'s `spend_probability` is a real,
running instance of `P(action | state, incentives, constraints,
environment)`:

```python
balance_ratio = balance / income_monthly
balance_factor = 0.5 + 0.5 * min(1.0, balance_ratio / 1.0)   # constraint
risk_factor    = 0.7 + 0.9 * risk_preference                  # preference
prob = 0.35 * balance_factor * risk_factor                    # incentive (base rate)
```

— not a black box, and not a category-level draw. Every factor is a named,
provenance-labeled constant (`Simulation/world/agents/person.py`), and the
function's output is a genuine function of *this* agent's own current
state, re-evaluated fresh every tick.

**How correlated behavior emerges, concretely, not hypothetically**: the
research prompt's example chain (income shock → liquidity reduction →
lower consumption → missed repayment → credit deterioration → future
borrowing constraint) decomposes into single-step mechanisms, and
`Simulation/` has already built and *measured* the first three steps of
exactly this chain:

```
lower balance                         [state, per-agent, from world-generation
                                       or from a run of bad luck/spending]
    ↓  (spend_probability's balance_factor term)
lower purchase attempt probability     [BUILT: person.py]
    ↓  (post_transfer's balance check)
higher chance a still-attempted purchase fails  [BUILT & MEASURED:
                                       Memory.md's balance-ratio table --
                                       96.25% failure rate at ratio<0.02,
                                       0.00% at ratio>=0.25, monotonic
                                       across 3 independent seeds]
    ↓  [PROPOSED, NOT BUILT]
"credit deterioration"                 (Research.md Part C.2: a credit_score
                                       field that decrements on
                                       payment_failure)
    ↓  [PROPOSED, NOT BUILT]
"future borrowing constraints"         (Research.md Part C.3: interest_rate
                                       = base_rate + risk_spread(credit_score))
```

The first half of this chain is not a design claim — it is a measured
property of a real run, reported with an honest caveat this document
should preserve rather than smooth over:
`Simulation/docs/Memory.md` also found that bucketing by *income level*
instead of *balance ratio* shows almost no signal (below-median-income
persons failed *less* often, 0.94% vs 1.15%, in the 500-person run),
"because purchase size scales with the buyer's own income... it's
specifically the ratio of balance-to-income at the moment of the attempt
that carries the signal, not income level or balance level alone." This is
exactly the kind of finding a synthetic-dataset generator with hand-coded
correlations would be unlikely to discover, because nobody would have
thought to encode "the confound goes this specific direction" as a rule —
it fell out of the mechanism's actual computation.

**What influences each named behavior, and status**:

| Behavior | Variables the literature/current build treats as relevant | Status |
|---|---|---|
| Spending | balance, income, risk preference | **[BUILT]** — `spend_probability` |
| Saving | income (fixed fraction swept) | **[BUILT, but not a decision]** — `SAVINGS_SWEEP_FRACTION` is a fixed mechanical sweep, not a person choosing to save more or less based on anything |
| Borrowing | credit score, income, existing debt, purpose | **[PROPOSED]** — Research.md Part C.3 |
| Repayment | balance at due date, obligation size, competing obligations | **[PROPOSED]** — no Obligation object exists yet (Working Section 2) |
| Fraud | account compromise state, not the legitimate owner's own decision | **[PROPOSED]** — Research.md Part C.1, explicitly modeled as *not* a Person-agent decision |
| Investment | risk tolerance, time horizon, expected return | **[NOT MODELED, NOT PROPOSED]** — no Markets domain exists in any form yet |
| Default | cumulative missed obligations, credit state | **[PROPOSED]** — depends on Obligation + credit-score machinery, neither built |
| Retries | prior failure, elapsed time since, expected liquidity recovery | **[NOT BUILT]** — `Simulation/docs/Memory.md`: "No retry behavior at all — a failed purchase is terminal... explicitly Phase 4" |
| Refunds | dispute outcome, merchant policy | **[NOT MODELED]** |
| Merchant pricing | none currently — `category` is "a cosmetic label only... does not affect any probability or behavior" per `merchant.py`'s own module docstring | **[PLACEHOLDER]** |
| Bank lending | capital adequacy, risk appetite, funding cost | **[NOT MODELED]** — no lending mechanism exists (Bank only ever receives and forwards money) |
| Liquidity management | reserve levels relative to policy targets | **[NOT MODELED]** — `bank_reserve` is monotonically non-decreasing by construction, per `bank.py`'s docstring, specifically because nothing draws it down in current scope |

## Working Section 7 — Institutions

`NORTH_STAR.md` §11's warning against `Bank.generate_transaction()` is
worth testing directly against what `Simulation/world/agents/bank.py`
actually is: it is not that — a Bank agent maintains a real Account
registry, a real double-entry `_post()` primitive enforcing the accounting
identity on every call, and a distinct asset-side `bank_reserve` account
representing "cumulative external cash it has received on behalf of its
depositors" (module docstring). That is a small, real instance of
`NORTH_STAR.md` §11's "LEDGER" and part of "TREASURY" — genuinely
internal institutional machinery, not a disguised random-row generator.

Mapping `NORTH_STAR.md` §11's full institutional-systems list against
what exists:

| System | Status in `Simulation/` |
|---|---|
| Customer System | **[BUILT, minimal]** — `person_account`/`person_savings_account` lookups in `engine.py` |
| Account System | **[BUILT]** — `Bank.accounts`, `open_account`/`open_reserve_account` |
| Payment System | **[BUILT, minimal]** — `post_transfer`, purchase flow |
| Credit System | **[NOT BUILT]** — no lending exists |
| Ledger | **[BUILT]** — full double-entry, tested (`tests/test_ledger.py`) |
| Treasury | **[PARTIALLY BUILT]** — `bank_reserve` is a real asset account, but there is no treasury *decision* (no funding cost, no active liquidity management) |
| Liquidity Management | **[NOT BUILT]** — reserve is monotonically non-decreasing by construction |
| Risk | **[NOT BUILT]** — for the *simulated* Bank's own risk function (not to be confused with `financial_system/`'s Risk module, a different system entirely) |
| Fraud | **[NOT BUILT]** |
| AML | **[NOT BUILT]** |
| Settlement | **[BUILT]** — pending → settled, T+1, `_run_settlement` |
| Compliance | **[NOT BUILT]** |
| Policy | **[NOT BUILT]** — no institutional policy object exists to vary |

**Institutional policy → cascading system behavior**, the pattern
`NORTH_STAR.md` §7 names as "the level of systemic behavior we want," is
currently **[NOT BUILT AT ALL]** — there is no policy object anywhere in
`Simulation/` for any institution to change, so nothing like "bank changes
credit policy → approval probability changes → ... → bank credit losses
change" can happen yet, honestly, not even in a toy form. This is worth
naming as a real gap rather than glossing past it: it is arguably the
single most valuable *next* institutional capability, because it is the
mechanism through which Working Section 15 (scenario generation) and
Working Section 25 (the simulation laboratory) become genuinely useful —
without a policy object to vary, "run the same world under two different
bank policies and compare outcomes" has nothing to attach to.

**Organization's payroll as the one real institutional-cascade instance
today**: `Simulation/world/models.py`'s `Organization` (Phase 2.5, A.3)
is worth calling out specifically, because it is a small, real, tested
proof that an institution's own state can causally constrain an agent's
outcome: an Organization-employed person's salary is "a genuine
`post_transfer` from that [Organization's revenue] account, not the
synthetic `employer:<id>` convention, so payroll can, in principle, fail
if underfunded" (`Phases.md`). `Memory.md` confirms the failure path is
mechanically real (checked atomically against the org's own balance,
recording a `payment_failure` exactly like a purchase failure) even
though it did not fire in the session's example run, "by generous design,
not by structural prevention." This is a genuine, if minimal, institution
whose own internal state (its revenue account balance) can causally
determine an agent-level outcome — the seed of exactly the cascade
`NORTH_STAR.md` §7 describes, one level deep.

## Working Section 8 — Economic Mechanisms

For each mechanism the research prompt names, what's built, what's real
research (via `Research.md`), and what's an open assumption:

**Liquidity constraints** — **[BUILT & MEASURED]**. This is the one
mechanism this whole project exists to demonstrate. Cause: an agent's own
balance relative to a pending obligation. Variables: `balance`,
`income_monthly` (via the ratio). Rule: `post_transfer`'s hard balance
check. Evidence: the measured monotonic failure-rate curve
(`Memory.md`). Assumptions: purchase size as a fixed fractional range of
the buyer's *own* income, independent of income level — and `Research.md`
Part A §1 already names, honestly, exactly where this assumption breaks
against real data (BLS CE quintile data: poorer households spend a
*larger* share of income, which this simulation's `purchase_amount()`
does not currently reproduce — confirmed as a real, measured GAP by
`validation/report.py`'s `check_spend_income_ratio_by_income`, not just
predicted in prose). Conditions under which it fails: exactly this — when
purchase size should scale inversely with income and doesn't.

**Credit creation, default, bank runs, risk pooling, insurance, market
formation, network effects** — **[NOT BUILT]**, none has any mechanism in
`Simulation/` today. `Research.md` Part C provides research-grounded
groundwork for the closest three (fraud, credit scoring, loan pricing) —
see Working Section 9 below for how that research does and does not
translate to executable rules.

**Interest / pricing** — **[NOT BUILT]** as a live mechanism, but
`Research.md` Part A §4 already assembled the real structural fact a
future implementation should use: "`interest_rate = base_rate +
risk_spread(person)`... exactly how the Fed's own Sept 2025 FEDS Note
describes real consumer lending," with a cited elasticity (~5bps of APR
per 100bps of regional default risk for unsecured credit, ~30bps for
mortgages) — genuinely useful, cited groundwork for Working Section 9's
pipeline, correctly not yet turned into code (Part C.3's own "why not
built now": it needs a `Loan` object and a bank capital-adequacy decision
Phase 2's ledger design never addressed).

**Inflation, unemployment, aggregate consumption/saving/investment** —
**[NOT BUILT]**, and arguably premature: these are macro-level phenomena
that, per Working Section 22, should be *emergent* from micro-level agent
behavior once enough of that behavior exists, not separately modeled as
top-down mechanisms layered on top. Building an "inflation mechanism"
before there is a real market/pricing layer for it to act on would be
exactly the premature-complexity failure mode Working Section 32 argues
against.

**Reserve requirements / bank liquidity constraint on lending** — a
specific, useful *negative* finding, already in `Research.md` Part A §5
and worth restating here because it corrects an intuitive-but-wrong
default design: "as of March 26, 2020, the Federal Reserve Board reduced
all reserve requirement ratios to zero percent... any future
lending-capacity constraint should be modeled on Basel/LCR-style capital
adequacy concepts instead" — not the classical fractional-reserve model a
naive design would likely reach for first.

**The general discipline this section reinforces**: for every mechanism
above, the honest answer to "what causes it / what variables influence it
/ what equations describe it / what evidence supports it / what
assumptions are required / what conditions cause it to fail" is either a
real, cited, checkable answer (liquidity constraints, and the loan-pricing
structure per Research.md) or an explicit "not built, and here is
specifically why not yet" — never a plausible-sounding rule adopted
because it would make the simulator feel more complete. This is
`Simulation/docs/Rules.md` #2 and #5 applied at the mechanism-design
level, not just the constant-value level.

## Working Section 9 — Research → Mechanism → Simulator

`Simulation/`'s Research.md/Memory.md work is a real, if partial and
manual, instance of the research prompt's own pipeline. Walking one
concrete case (settlement delay) through every named stage:

```
PAPER/INDUSTRY DOCUMENT   Stripe's public documentation: "settlement
                          typically takes one to three business days
                          after the transaction"
       ↓
DISCOVERY (manual, this session, via WebSearch/WebFetch --
       NOT Discovery.AI itself; see the honest caveat below)
       ↓
CLAIM      "real card-network settlement is genuinely delayed, on the
           order of 1-3 business days, not instant"
       ↓
FORMALIZATION   settlement_delay ∈ [1, 3] business days (a range, not a
                point estimate)
       ↓
SIMULATION COMPONENT   Simulation/world/engine.py's _run_settlement:
                       fixed T+1 (the low end of the cited range)
       ↓
CALIBRATION   T+1 chosen deliberately, not derived: "kept as-is... T+1
              already sits inside the real, cited range (at its
              low/most-conservative end)" (Research.md Part B) --
              and *why* not a random 1-3 day draw is itself recorded
              (would perturb the RNG sequence Phase 2 deliberately
              protected)
       ↓
VALIDATION   validation/report.py's check_settlement_timing confirms,
             on real output, that every settlement lands exactly T+1 --
             i.e. the code does what the (documented, honest) design
             decision says it does
```

Every stage is real and traceable to a file. What is **[NOT BUILT]** is
the automation of any of it: the "DISCOVERY.AI" box in this pipeline was,
in this case, a human-directed research session using WebSearch/WebFetch
manually, producing a written document (`Research.md`) that a human then
read before making one narrow, cited code change. There is no
`Discovery.AI`-equivalent module in this repository that autonomously
scans new research, proposes a mechanism, and stages a code change for
review — that is exactly `NORTH_STAR.md` §8-9's proposed role for
Discovery.AI, and it remains entirely proposed.

**The per-mechanism record this pipeline requires, tested against a real
example**: `Research.md`'s settlement-delay entry actually carries every
field the research prompt asks for — source (Stripe's page, named and
linked), claim (settlement is delayed, 1-3 days), formalization (a range),
assumptions (uniform application, no per-network variation), parameters
(T+1), parameter source (chosen within the cited range, not derived from
it), calibration (deliberately not RNG-varied, with the reason stated),
uncertainty (explicitly: "no source... says every merchant settles in
exactly 1 day"), validity range (implicitly, card-network payments;
explicitly not claimed for other settlement types), known limitations
(named in the same docstring). **[DESIGN OPINION]**: this record currently
lives as unstructured prose across a docstring and a markdown file. A
genuinely reusable research-provenance system (`NORTH_STAR.md` §34) would
need this as a structured, queryable object per mechanism — not a
different discipline, the same discipline made machine-readable.

**This prevents the failure mode named in the research prompt** —
"uncontrolled hallucination engine" — concretely: `Research.md`'s own
"deliberately NOT changed, and why" section is the single best evidence in
this repository that the discipline works under pressure, not just in
principle. A tempting, nearly-matching number (`sigma≈0.5` from a
wage-inequality paper, coinciding almost exactly with the simulation's
existing constant) was found and explicitly *not* adopted, for two stated
reasons (unverifiable source, population mismatch) — the harder and more
valuable outcome than simply reporting a match.

## Working Section 10 — The Role of Real Datasets

`Simulation/`'s own history already demonstrates the four roles the
research prompt names, cleanly separated:

- **Distribution estimation / calibration** — `Research.md` Part A/B:
  real published summary statistics (BLS CE spend/income ratios, Fed 2007
  credit-score distribution, FRBNY delinquency transition rates) used to
  check and, where clean enough, adjust existing mechanisms.
- **Validation / real-world comparison** — `validation/report.py`'s B.2
  section: compares simulated output against `Research.md`'s cited
  numbers and reports PASS/GAP honestly, including a real, measured GAP
  (spend/income ratio by income quartile) rather than only reporting
  passes.
- **Synthetic experiments** — the entire premise of `Simulation/` itself
  (the simulator *is* the synthetic-experiment generator; a real dataset
  cannot, by construction, contain a controlled counterfactual).
- **Benchmarks** — **[NOT USED]** in `Simulation/` today; the closest
  analog is `financial_system/`'s existing corpus, which this project was
  explicitly built to eventually improve on, not benchmark against
  directly (no such comparison has been run).

**"The dataset is a window into the world, not the definition of the
world," tested against this project's actual choices, not just asserted**:
`Simulation/docs/Rules.md` #3 ("No external dataset downloads without
explicit user approval... If a later phase genuinely needs a real dataset
[for calibration]... that is a new decision to bring back to the user
explicitly") is this exact principle, operationalized as a hard rule
*before* any research session happened — and `Research.md`'s "What was not
downloaded, and why" section shows it held even once external research was
explicitly authorized: "No dataset was bulk-downloaded... every number
needed... was obtainable from a published summary without touching raw
microdata." The FRBNY Consumer Credit Panel, BLS CE public-use microdata,
and DCPC day-level datasets were all identified as available and
deliberately not fetched. This is the dataset-as-window principle actually
being chosen over the easier, more tempting path (bulk download the real
data, sample from it directly) — worth stating plainly because "define
the world from real data" is usually the *faster* engineering path, and
this project's own history shows the harder path being chosen on purpose,
twice (Phase 1's initial design, and this later research session).

## Working Section 11 — Build the World Generator

`Simulation/world/engine.py`'s `_build_world` is a complete, working
instance of the research prompt's pipeline, in miniature — walked stage by
stage against the actual code:

```
WORLD CONFIGURATION      SimulationEngine.__init__'s parameters (seed,
                          num_persons, num_banks, num_merchants, num_days,
                          start_date) -- the entirety of Simulation's
                          current configuration surface
       ↓
INSTITUTION GENERATION    Banks created first (each gets a bank_reserve
                          account before anything else can be funded --
                          _build_world's ordering is itself meaningful,
                          not arbitrary)
       ↓
POPULATION GENERATION     Persons: income (log-normal), opening balance
                          (fraction of income), risk_preference (uniform),
                          payday (uniform 1-28) -- see Working Section 6's
                          table for provenance of each
       ↓
ENTITY RELATIONSHIPS      Org membership decided per-person (Phase 2.5);
                          Household grouping in a SEPARATE pass "so a
                          household-size decision doesn't perturb the
                          per-person RNG draw sequence" (engine.py comment)
                          -- a deliberate ordering choice to keep later
                          additions from silently changing earlier
                          outcomes
       ↓
INITIAL BALANCES          Opening balance seeded directly onto
                          Account.balance, explicitly OUTSIDE the ledger
                          (bank.py docstring: "world-generation initial
                          condition, not a simulated transaction")
       ↓
INITIAL CONDITIONS        Organization revenue accounts funded once, via
                          a real fund_external ledger transaction (unlike
                          opening balances -- a deliberately different,
                          more traceable choice, per this task's explicit
                          instruction, per Memory.md)
       ↓
AGENT POLICIES            [NOT PRESENT] -- no policy object exists to
                          initialize (Working Section 7)
       ↓
WORLD START               run() begins the day loop
```

**Dependency structure, not independent sampling**: the research prompt
explicitly warns against sampling every variable independently, and
`Simulation/`'s actual generation already avoids the naive version of that
mistake in two concrete ways. First, opening balance is *not* independent
of income — it is drawn as `income * uniform(0.1, 1.0)`, i.e. a person's
starting cash is explicitly a function of their own income level, not an
unrelated draw. Second, Organization funding is computed *after* the
Person loop completes, specifically because it needs to sum the actual
incomes of that org's actual employees — a genuine dependency the code
respects by ordering (funding happens in a separate pass, once
`income_by_person` is fully known), not by chance. What is **[NOT
BUILT]**: any *cross-person* correlation structure (income is currently
drawn i.i.d. per person with no geography, no household-level income
correlation, no assortative matching of similar-income people into the
same household) — `Memory.md` names this directly: "Population generation
(income/balance/risk distributions) is IID per person with no geography,
household, or correlation structure — acceptable for Phase 1's... question,
but a likely first target if Phase 3 happens." Real households are not
income-independent draws (a household's members' incomes correlate through
shared housing costs, assortative marriage patterns, etc.) — this is a
named, real gap, not a silently accepted one.

## Working Section 12 — Build the World Evolution Engine

`Simulation/world/engine.py`'s actual day loop, mapped against the
research prompt's abstract pipeline:

```
CURRENT STATE           every Account's current balance (derived, per
                         Working Section 3)
      ↓
AVAILABLE EVENTS         [income arrival if payday, purchase attempt] --
                         a small, fixed menu per agent, not dynamically
                         computed
      ↓
AGENT DECISIONS           Person.maybe_receive_income /
                          Person.wants_to_spend, both deterministic
                          functions of state + one seeded RNG draw
      ↓
EVENT SELECTION           [IMPLICIT -- the engine tries every available
                          event type for every agent every tick, gated by
                          each event's own probability function; there is
                          no separate "choose among competing events"
                          step because Phase 1's agents never have two
                          mutually exclusive events to choose between]
      ↓
EVENT EXECUTION            post_transfer / fund_external -- the balance
                           check IS the execution-time validity check
      ↓
STATE TRANSITION            Account.balance updated inside _post(), in
                            the same call that appends the LedgerEntry
      ↓
NEW STATE                    the next tick's CURRENT STATE
      ↓
NEXT EVENTS                   [IMPLICIT -- same fixed menu, re-evaluated
                              next tick against the new state]
```

**Discrete-event vs. time-stepped, and which fits finance**:
`Simulation/` chose time-stepped (one tick = one simulated day,
`Simulation/world/clock.py`'s own docstring: "Phase 1 uses ticks... no
wall-clock time is ever read"), not a general discrete-event queue with
arbitrary inter-event timing. **[DESIGN OPINION]**, but a reasoned one: for
a world whose finest-grained real institutional rhythm (settlement
batches, daily interest accrual, end-of-day reconciliation) is itself
day-granular, time-stepped simulation is not a simplification that loses
information — it matches the actual cadence of the phenomena being
modeled. A general discrete-event simulation (arbitrary continuous-time
event scheduling, a priority queue ordered by event time) becomes
necessary once sub-day timing genuinely matters — e.g. modeling
authorization-then-capture within a single payment's lifecycle (seconds to
minutes apart), or intraday liquidity management (a bank's minute-by-minute
cash position). Neither exists in `Simulation/` today, so the time-stepped
choice has not yet been tested against a case that would break it — worth
flagging as the concrete trigger condition for revisiting this choice,
not "eventually, for generality."

**Causal ordering / simultaneity, already handled, not hand-waved**: within
one tick, `_run_one_day()` runs settlement *before* that day's Person loop,
specifically "so that ordering is what makes the sweep exactly T+1" (code
comment). Within the Person loop, persons are iterated in a **fixed,
seed-independent order (creation order)**, every tick, on every run — the
engine's own module docstring states this is "required for determinism."
This is the actual, working answer to "how are simultaneous events
ordered": deterministically, by a stated, fixed rule, never by wall-clock
race or by any order dependent on the RNG itself. Temporal consistency
(Working Section 18's later concern) is a natural consequence of this
ordering discipline plus the single-seeded-RNG discipline
(`Simulation/docs/Rules.md` #6) — not a separately bolted-on guarantee.

## Working Section 13 — Institutions and Markets as Networks

`Household`, `Organization`, and `Community` (`Simulation/world/models.py`,
Phase 2.5) are real network structures — a Household is a set of Person
nodes connected by shared-account edges; an Organization is a set of Person
nodes connected by employment edges to one institution node; a Community is
a set of Household/Organization nodes grouped by an inert containment edge.
All three exist, all three are tested (`tests/test_phase25.py`), and — this
is the honest and important part — **none of the three currently influence
any agent's decision function**. `Community`'s own docstring states this
most explicitly: "It exists purely so a future session could aggregate/
analyze at the community level if a real reason to do so ever appears — it
drives nothing in this simulation today," and `Memory.md` records the test
that proves it structurally, not just in prose ("no `community_id` ever
appears as any Transaction's `from_id`/`to_id`... proven structurally
inert on real output, not just claimed inert").

This is worth dwelling on because it is exactly the gap between "a network
structure exists" and "network structure drives emergent phenomena" that
the research prompt's own Working Section 22 (Emergence) cares about most.
`Simulation/` has the *data structure* for network effects — a household's
members are genuinely linked, an org's employees are genuinely linked to
one revenue account — but has not yet built the *mechanism* layer on top:
no household-level shared liquidity effect (e.g. one member's balance
crisis affecting another member's spending), no organization-level
correlated-income-shock effect (e.g. all of one org's employees suffering
simultaneously if that org's revenue account runs low — currently, per
`_maybe_pay_income`'s atomic all-or-nothing check per payday, an org
funding shortfall *would* actually produce correlated payroll failures
across every employee paid that day, which is a real, if accidental,
first instance of network-driven correlated failure — but this was not the
design's explicit purpose and hasn't been exercised or measured).

**How topology influences fraud/AML/liquidity/contagion/systemic risk —
`[PROPOSED]`, none built**: the research prompt's list (ownership networks,
payment networks, counterparty networks, beneficial-ownership networks) is
squarely `NORTH_STAR.md` §6/§13 territory (a "Relationship Registry," AML
domain expansion) and entirely unbuilt here. The one concrete, buildable
next step this document can honestly recommend, grounded in what already
exists: `Simulation/`'s own transaction log already *implicitly* contains a
payment network (every `Transaction.from_id → to_id` edge, weighted by
frequency and amount) — nothing currently extracts or analyzes it as a
graph. That is a genuinely small, low-risk next step (a pure read-only
analysis over existing output, no simulation-loop change) compared to
building a *causal* network mechanism that feeds back into agent behavior,
which is a substantially larger undertaking.

## Working Section 14 — Model Shocks

**[NOT BUILT]** in any form — `Simulation/` has no shock-injection
mechanism today; every run proceeds under the same fixed-at-generation-time
world configuration for its entire duration. This is worth stating plainly
rather than inferring "probably possible" from the fact that constants
exist: there is no code path anywhere that changes a constant mid-run, and
no event type represents an exogenous shock.

The research prompt's warning — "do NOT simply directly write `fraud_rate
= 0.4` without modeling the mechanism" — maps cleanly onto a discipline
`Simulation/` already enforces for *ordinary* mechanisms
(`Simulation/docs/Rules.md` #2) and should extend to shocks specifically:
a shock is not a parameter override, it is an *event* (in Working Section
4's sense) that changes an entity's or institution's *state*, which then
changes behavior *through the existing mechanism*, not by a special-cased
"if shock_active: behave differently" branch. Concretely, for the
liquidity-constraint mechanism that already exists: an "unemployment
shock" should be modeled as an event that sets a fraction of Persons'
`maybe_receive_income` to return `0.0` for some number of ticks (their
payday no longer produces salary) — the *existing* `spend_probability`
mechanism would then, with zero new code in the behavioral layer, produce
lower spend probability and higher failure rates for exactly the affected
population, because that mechanism already responds correctly to a lower
balance. This is the concrete, buildable pattern a shock-injection layer
should follow: **shocks change entity state at a scheduled event; they
never directly assign a behavioral outcome probability.**

None of the specific shocks the research prompt lists (interest-rate
change, bank failure, payment-network outage, regulatory change) has a
natural home yet, because most require machinery that doesn't exist
(interest rates: no loan mechanism; bank failure: no bank-solvency state at
all, `bank_reserve` being monotonically non-decreasing by construction
specifically rules this out today; regulatory change: no Policy object,
Working Section 7). The unemployment-shock example above is deliberately
the one chosen for illustration because it is the one shock type whose
entire causal path already exists in the codebase today — everything else
in the shock list requires new mechanism-building first.

## Working Section 15 — Build Scenario Generation

`Simulation/`'s current configuration surface (`run_simulation.py`'s CLI
flags: `--seed --population --banks --merchants --days --start-date
--outdir`, per `Memory.md`) already supports exactly one scenario type
cleanly: **BASELINE WORLD**, parameterized by population size and run
length, with a seed controlling the specific instantiation. Every other
scenario type the research prompt names is **[NOT BUILT]**:

| Scenario type | What it would need that doesn't exist today |
|---|---|
| Baseline | **[BUILT]** — exactly what the current CLI produces |
| Calibrated | A calibration loop (Working Section 20) whose output *feeds back* into the CLI's parameters — today's parameters were chosen once, by research + judgment, not re-fit against a target dataset in a loop |
| Stress | A shock-injection layer (Working Section 14) |
| Adversarial | Working Section 26's search loop |
| Counterfactual | Working Section 16's world-branching |
| Historical | A time axis genuinely anchored to real calendar dates *and* real economic-regime data for that period — today's `start_date` only controls day-of-week/day-of-month calculations, not any economic conditions |
| Hypothetical | Already trivially possible in the loosest sense (any parameter combination is "hypothetical"), but not distinguishable from Baseline without a Policy/Mechanism-version axis to vary deliberately |

Every scenario type the research prompt asks each configuration to specify
(initial conditions, mechanism versions, parameters, seed, shocks,
policies, populations) maps onto real fields for exactly two of those —
seed and population size — today. Mechanism versions and policies don't
exist as separate, swappable objects at all (a "mechanism" today is a
Python constant + function baked into `person.py`/`engine.py`, not a
first-class, versioned, selectable component) — this is the single biggest
structural gap between what exists and what full scenario generation
needs, and it is the same gap Working Section 27 (Reproducibility) names
independently from a different angle (`mechanism_versions` has nowhere to
live because mechanisms aren't yet objects with identity separate from
"the current state of this file").

## Working Section 16 — Build Counterfactual Worlds

**[NOT BUILT]** — no cloning or branching mechanism exists. But
`Simulation/`'s architecture already has the one property that makes
counterfactual worlds *cheap* to build later, rather than requiring a
redesign: because the entire world state is a pure function of `(seed,
configuration, event history up to some day)` — no wall-clock reads, no
hidden global state (`engine.py`'s own module docstring states this
explicitly as a design requirement) — a world at time `t` is, in principle,
just "replay the same seed and configuration for `t` days." Branching at
`t` then means: replay identically for `t` days (guaranteed
byte-identical, per the determinism tests), then apply exactly one
intervention, then let the *same* seeded RNG instance continue drawing from
wherever it left off.

**The one real design question this surfaces, worth naming honestly**:
"only the intervention should differ unless stochastic divergence is
intentionally modeled" is harder than it sounds given `Simulation/`'s
current single-shared-RNG design. Today, exactly one `random.Random(seed)`
instance is threaded through *every* draw for *every* agent, in a fixed
iteration order (Working Section 12). If a counterfactual branch's
intervention is, say, "give Person X an extra $500 at day 10," every
downstream RNG draw from that point forward is still consumed in the same
order — but if the intervention instead changes *how many* RNG draws some
step consumes (e.g. "Person X now also considers a second purchase option,
consuming one more `rng.random()` call than the baseline branch did"), every
subsequent draw across the *entire population*, not just Person X, would
silently shift, because the single shared RNG stream has no per-agent
isolation. This is not a hypothetical concern — `Simulation/`'s own Phase
2.5 build notes name exactly this failure mode as something they had to
actively design around ("a SEPARATE pass over the already-built
self.persons list... specifically so a household-size decision doesn't
perturb the per-person RNG draw sequence"). A real counterfactual-branching
system would need either (a) a per-agent RNG stream (each agent seeded
deterministically from a hash of `(world_seed, agent_id)`, so one agent's
extra draw cannot perturb another's), or (b) a strict invariant that no
intervention may change the *number* of RNG draws any unaffected agent
consumes. This is a genuine, non-trivial architectural decision for
whenever counterfactual worlds are actually built — recorded here as an
open design question (Working Section 30 returns to it), not resolved.

Uses this would unlock, once built: policy testing ("what if
`ORG_FUNDING_SAFETY_MULTIPLIER` had been 1.0 instead of 1.2 — how many
more organizations would have had a real payroll failure, holding
everything else identical"), which is directly checkable against
`Simulation/`'s own existing, honestly-reported finding that payroll
failure "did not occur in this session's example run... the funding
buffer is deliberately generous" — a counterfactual world is precisely the
tool that could turn "did not occur" into "would occur under condition X,"
which the current single-branch simulator cannot answer.

## Working Section 17 — Build Monte Carlo World Sampling

**[NOT BUILT]** as a system, but `Simulation/`'s own development process
already performed a manual, ad hoc instance of it, worth citing as
evidence the underlying capability (run many seeds, check whether a
finding holds) is cheap and already informally proven out:
`Simulation/docs/Memory.md`'s "Robustness check across seeds" section
re-ran the balance-ratio finding at seed=7 and seed=2026 (300 persons, 90
days each) specifically to check the headline finding "wasn't a fluke of
seed=42," and reports the resulting table across all three seeds side by
side. That is literally `W₁, W₂, W₃` from a parameter distribution
(different seeds, same configuration), with a hand-computed statistic
compared across them — Monte Carlo sampling, done manually, once, for one
question.

What a real system needs beyond this: (1) sampling over *configuration*
parameters, not just seed (today, `INCOME_LOGNORMAL_SIGMA` or
`ORG_FUNDING_SAFETY_MULTIPLIER` could in principle be swept the same way
seed already is, but no harness does this automatically); (2) automated
aggregation and reporting across the sample (today's cross-seed check was
a manual table built by hand, not a script); (3) importance/rare-event
sampling for tail phenomena (e.g. "sample worlds where an Organization
payroll failure actually occurs" — currently would require brute-force
random search since payroll failure is deliberately rare by design, per
`ORG_FUNDING_SAFETY_MULTIPLIER`'s own docstring). **[DESIGN OPINION]**: item
(1) is the natural, low-risk next step given how close the pieces already
are (the engine already accepts a seed and constructs a fresh, isolated
world per instantiation — sweeping any other constructor parameter the
same way is a small extension, not a redesign); (3) is a materially harder
problem this document does not claim a ready design for.

## Working Section 18 — Define Observability

**[NOT BUILT, but exactly the right next generalization target]** — this
is the sharpest gap between what `Simulation/` does today and what
`NORTH_STAR.md` §5 asks for at Heimdall scale. Today, the simulator's
entire output — every account balance, every ledger entry, every
transaction, at any point in the run — is written to CSV and is, by
construction, fully visible to anything that reads that output. There is
no concept of "what a given observer, at a given time, with a given scope,
would actually have been allowed to see." `Simulation/`'s own honest
framing already names this precisely, in a different but directly
analogous context: `Memory.md`'s balance-ratio table is computed *by the
report script, after the run, with full access to every agent's true
balance at the moment of every attempt* — i.e. `stats/report.py` and
`validation/report.py` both currently operate as an omniscient observer,
which is fine for their actual purpose (auditing the simulator's own
mechanism) but would be exactly wrong as a stand-in for what a real
financial intelligence system observing this same world should be allowed
to see.

`NORTH_STAR.md` §5 already states the target primitive precisely
(`WorldSnapshot(as_of=t, observer=X, scope=Y)`), and — this is the concrete
connection worth making explicit — `financial_system/`'s existing Risk
temporal-leakage fix (Block 5, cited in `NORTH_STAR.md`'s own "Already
prefigured" section) is a working, tested instance of exactly this
principle, in one domain, applied to Heimdall's *real* system rather than
the simulator. What `Simulation/` would need to generalize the same
principle to a *simulated* world: (1) a distinction between the
simulator's own internal state (every ledger entry, at full precision,
always) and a *view* of that state constructed for a specific observer at
a specific simulated time, filtered to only events at or before `as_of`
and only entities/fields within `scope`; (2) enforcement, not just
convention — today, nothing prevents `validation/report.py` (or any future
Heimdall-facing consumer) from reading a transaction dated after the
`as_of` it claims to be reasoning from, because no such concept exists to
violate. This is not a hard technical problem given the event-sourced
design already in place (an event-sourced world is, in fact, unusually
well-suited to this: "state at time t" is already computed by filtering
events to `occurred_at <= t`, per Working Section 4's `State(t+1) =
Transition(State(t), Event(t))` — the *filtering* machinery, not the
concept, is what's missing) — but it is real, unbuilt work, not a trivial
follow-on.

## Working Section 19 — Define Ground Truth

**[BUILT, structurally, but not yet exploited as a distinct capability]** —
every simulated world, as it stands today, already *has* a complete,
known causal history in exactly the sense the research prompt means: every
`payment_failure` row's true cause (`balance_before < amount`, at that
specific moment, for that specific agent) is not just knowable in
principle but literally checked by an automated test
(`tests/test_engine.py`'s payment_failure assertions,
`validation/report.py`'s `check_causal_balance_ratio`). This is real
ground truth a real dataset cannot have — no real transaction log carries
a verified, machine-checkable field proving *why* each failure happened,
because the real world's generating mechanism was never a piece of
software whose invariants could be asserted.

What's missing is the deliberate *separation* the research prompt asks for
between this ground truth and what an intelligence system is allowed to
see (Working Section 18) — today, ground truth and observation are the
same thing, so "rigorous evaluation of fraud detection / AML / causal
inference / investigation without leaking ground truth" (the research
prompt's own stated purpose for this distinction) is not yet possible to
do honestly with this simulator's output: any evaluation run against
today's CSVs would necessarily be evaluating against data that already
contains what should have been hidden. This is the same gap as Working
Section 18, viewed from the ground-truth side rather than the observer
side — they are two names for one missing capability, and building the
observation-boundary layer (Section 18) *is* what would let ground truth
finally be used as ground truth rather than as the only available view.

## Working Section 20 — Build the Calibration Loop

`Simulation/`'s actual calibration history is a real, if manual and
narrow, instance of the research prompt's loop — walked stage by stage:

```
REAL DATA                BLS Consumer Expenditure Survey 2024, Stripe's
                          public settlement documentation, etc.
                          (Research.md Part A)
       ↓
DISTRIBUTION ESTIMATION   "overall spend/income ratio of about 75%,"
                          settlement "1-3 business days" (Research.md)
       ↓
SIMULATOR PARAMETERS      candidate swap targets identified:
                          INCOME_LOGNORMAL_SIGMA, BASE_DAILY_SPEND_PROB,
                          OPENING_BALANCE_FRACTION_RANGE, settlement delay
       ↓
SIMULATION                [not separately re-run for this step -- the
                          existing baseline run's output was the
                          comparison target]
       ↓
COMPARE                   Research.md Part B, parameter by parameter
       ↓
CALIBRATE                 ONE change made (settlement-delay provenance
                          label, not its value); THREE changes explicitly
                          rejected, each with a stated reason (unverifiable
                          source, definitional mismatch, no clean number to
                          substitute) -- Research.md Part B
```

**What was and wasn't calibrated, and why that's the correct outcome, not
an incomplete one**: `Research.md`'s own "Honest overall summary" states
this exactly — "Part B's actual code footprint is intentionally small...
because, on close inspection, none of the four eligible existing
parameters had a research finding that was BOTH clean AND cleanly mapped
onto exactly what that parameter models." This is worth treating as the
research prompt's own instruction — "determine what cannot be confidently
calibrated" — already answered, concretely, for four real parameters, not
left as an abstract caveat. Marginal distributions (income shape) were
judged already well-supported and left alone; conditional relationships
(spend-as-fraction-of-income *by income level*) were found to have a real,
well-sourced gap that a single constant swap cannot fix (Working Section
8); event frequencies (base spend probability) had a promising real lead
(DCPC's zero-payment-day statistic) that failed independent verification
in this session specifically, not in principle — flagged as worth
revisiting, not abandoned.

**What a full calibration *loop* (as opposed to a one-time calibration
pass) would add, unbuilt today**: automatic re-fitting (adjust a parameter,
re-run, re-compare, iterate) rather than a single manual pass; this
requires the Monte Carlo sampling infrastructure of Working Section 17 to
be efficient enough to run inside a loop, and a formal loss/distance metric
between simulated and real distributions (today's comparison is a
human-read table, not a scored objective) — neither exists yet.

## Working Section 21 — Validation at Multiple Levels

`Simulation/`'s `validation/` package (Phase 2.5, Part B) already
implements a real instance of several of the research prompt's levels,
distinct and separately labeled — mapped explicitly:

| Level | Research prompt's question | `Simulation/`'s instance | Status |
|---|---|---|---|
| Micro | Does individual behavior resemble reality? | `check_causal_balance_ratio` — an individual agent's failure probability as a function of their own state | **[BUILT]** |
| Meso | Do institutions/networks behave realistically? | `check_organization_payroll_traceability`, `check_household_accumulation` | **[BUILT, narrow]** — checks internal consistency of the institution's own mechanics, not yet "does this resemble a real institution's behavior," since no real-institution comparison data exists for these specific mechanics |
| Macro | Do aggregate patterns emerge realistically? | `check_income_distribution_shape`, `check_spend_income_ratio_by_income` | **[BUILT]** — and this is the level that produced the project's one real, honestly-reported GAP |
| Temporal | Do dynamics over time resemble reality? | `check_settlement_timing` | **[BUILT, narrow]** — one specific temporal pattern (T+1), not general temporal-dynamics validation (e.g. no check of whether balance *trajectories* over a run look realistic) |
| Causal | Do interventions produce plausible effects? | **[NOT BUILT]** — no intervention/counterfactual capability exists yet (Working Section 16), so nothing can be checked at this level today |
| Distributional | Do generated observations resemble empirical data? | `check_income_distribution_shape` (compares shape, not just presence) | **[BUILT]** |

`validation/report.py`'s own internal/external split (B.1 mechanism
consistency vs. B.2 comparison against `Research.md`'s real numbers) is
itself a real instance of the research prompt's core distinction — B.1
checks are "does the simulator's own math hold" (double-entry invariant,
no negative balances — checks that would pass by construction on *any*
correctly-coded run, real or fabricated data alike) while B.2 checks are
"does the simulator's *behavior* resemble something real" (the only
checks that can actually fail against ground truth, and the only ones
where a PASS is informative rather than tautological). `Memory.md`
explicitly names this exact hazard from its own build process: "An early
version of this check used a small absolute-percentage-point threshold and
produced a false PASS on pure sampling noise — caught and fixed before
this was finalized." This is not "the CSV looks realistic" — it is a
documented instance of catching a validation check that would have
produced exactly that shallow, wrong kind of confidence, and fixing it
before shipping.

**What genuinely does not exist**: causal-level validation (no
counterfactual capability to validate against), any comparison at the
network/topology level (no network mechanism exists to validate, per
Working Section 13), and any comparison against real *microdata* rather
than published summary statistics (a deliberate scope boundary, per
Working Section 10, not an oversight).

## Working Section 22 — Define Emergence

Testing the research prompt's own example chain (individual spending
decisions → aggregate demand → merchant revenue → business failures →
employment changes → consumer income) against what's actually built:

- **Individual spending decisions → aggregate demand**: **[BUILT]** —
  every purchase is a real agent decision, and aggregate demand (total
  purchase volume) is a real, computable sum over them, not separately
  modeled.
- **Aggregate demand → merchant revenue**: **[BUILT, trivially]** — a
  merchant's revenue *is* the sum of purchases routed to it (merchant
  selection is `self.rng.choice(self.merchants)` — uniform random, so
  today revenue differences across merchants are pure sampling noise, not
  driven by any merchant-side mechanism like pricing or reputation).
- **Merchant revenue → business failures**: **[NOT BUILT]** — a Merchant
  agent has no failure state, no minimum-viable-revenue concept, nothing
  that could make "this merchant's revenue was too low" have any
  consequence at all. `merchant.py`'s own docstring is explicit:
  "Merchants still have no spending behavior of their own... Merchants
  have zero behavior beyond receiving money" (`Memory.md`).
- **Business failures → employment changes → consumer income**: **[NOT
  BUILT]** — no chain exists past the point above, since its precondition
  (merchant failure as a real state) doesn't exist.

**What should be explicitly programmed vs. emergent, as a design
principle, tested against what already works**: `Simulation/`'s single
clearest success (the balance-ratio → failure-rate curve) is emergent in
exactly the right sense — nobody wrote "if balance/income < 0.02, fail 96%
of the time"; that number is a *consequence* of two independently
specified, much simpler mechanisms (`spend_probability`'s balance_factor
term, and `post_transfer`'s hard balance check) interacting over many
agents and many days. This is the pattern worth generalizing: **program
the local mechanism, not the aggregate statistic**. The failed converse is
equally instructive and equally real in this same codebase: `Community` was
*deliberately not* given a mechanism specifically to avoid programming an
aggregate-feeling "community effect" that wasn't backed by any local
mechanism (`models.py`'s own docstring: "inventing a 'community effect'
just to make it feel more complete would be exactly the unjustified
mechanism Rules.md #2/#5 warn against, and was explicitly declined"). That
is the correct discipline applied in the negative direction — resisting
the temptation to hand-author an emergent-sounding phenomenon rather than
building the local mechanisms that would actually produce it.

**Which systemic phenomena are plausible emergence targets, given what
exists**: merchant failure *could*, in principle, emerge from existing
machinery with a genuinely small addition (give Merchant a minimum
sustainable revenue threshold, checked against their own settled-account
balance trajectory — reusing the existing settlement/ledger infrastructure
entirely) rather than needing an entirely new subsystem. Aggregate
unemployment from correlated business failure is a much larger step
(needs Merchant→employment linkage, which doesn't exist even structurally,
unlike Organization→Person which already does).

## Working Section 23 — Connect Simulation to Heimdall

**[NOT BUILT, explicitly and deliberately]** — `Simulation/docs/Phases.md`
Phase 6 states this as plainly as a scope document can: "Whether and how
this simulation's output ever feeds into `financial_system/` is an
explicit decision to make later, with the user, once there's something
real to evaluate — not a default outcome of this project existing," and
`Rules.md` #4 makes the boundary a hard rule, not a soft intention:
"`financial_system/` is a locked, submitted, tested codebase — nothing
here imports from it, writes to it, or assumes it exists." Every session
recorded in `Memory.md`, across Phase 1 through Phase 2.5, confirms this
boundary held in practice, not just on paper ("`financial_system/` was not
touched anywhere," repeated verbatim at the end of every phase's section).

This document does not propose crossing that boundary — it stays exactly
as deliberately deferred as `Simulation/`'s own docs already say it is.
What is worth doing here, since the research prompt explicitly asks for
this connection to be designed, is naming *what the eventual bridge would
need to look like*, conditioned on everything documented above, without
building any of it:

```
SIMULATED WORLD (Simulation/, unchanged)
      ↓
WORLD STATE                event log + account state, as it exists today
      ↓
[NEW] OBSERVATION BOUNDARY  Working Section 18's WorldSnapshot(as_of, scope)
                            -- does not exist yet; this is the one genuinely
                            new layer this bridge needs BEFORE Heimdall
                            should be allowed to read any of it, per
                            NORTH_STAR.md §5's own standard applied
                            consistently
      ↓
HEIMDALL OBSERVATION        financial_system/'s existing Risk/Controller/
                            Recovery, reading a WorldSnapshot the same
                            shape as they'd read a real transaction feed
      ↓
RISK / INVESTIGATION / ECONOMIC REASONING / POLICY / ACTION
                            entirely financial_system/'s existing,
                            frozen, tested machinery -- unmodified
      ↓
[NEW] ACTION → SIMULATED INSTITUTION  an Action's outcome would need to be
                            able to write back into Simulation/'s world
                            state as a real event (e.g. a Recovery
                            decision "retry this payment" would need to
                            become a real retry attempt against the
                            simulated Person's actual current balance) --
                            this requires Simulation/'s own retry mechanism
                            to exist first (Phases.md Phase 4, not started)
      ↓
OUTCOME → WORLD UPDATE       the simulated world's own event-sourced state
                              update mechanism (Working Section 3/4) --
                              already the right shape for this, once an
                              Action can produce a real Simulation/ event
```

**What this bridge would require that doesn't exist on either side**: (1)
the observation-boundary layer (Working Section 18, Simulation-side, not
built); (2) a way for `financial_system/`'s Action layer to write an
event into a running `Simulation/` world rather than only reading a
finished CSV export (today `Simulation/` only ever produces a complete,
finished run — there is no notion of a paused, still-running world a
consumer could act into); (3) `Simulation/`'s own retry mechanism (Phase
4), since "Recovery decides to retry" has no target to act on without it.
None of these three exist. This is consistent with, not contradictory to,
`Rules.md` #4 and `Phases.md` Phase 6 — describing what a bridge would
need is not building one.

## Working Section 24 — Connect Simulation to Agent Training

**[NOT BUILT, and — per this document's own judgment — not yet clearly
justified]**. Working through the research prompt's own instruction
("determine which problems require which training paradigm," "do not
assume reinforcement learning is automatically the correct solution")
against what actually exists in `Simulation/` today:

- **Supervised learning** — would need labeled examples of a target
  quantity to predict. `Simulation/`'s output already has one genuinely
  clean label a supervised model could target honestly: `payment_failure`
  with its verified `balance_before < amount` cause — a model trained to
  predict failure probability from an agent's own visible state would be
  learning a *real*, verified mechanism, not a spurious pattern. This is
  the single most defensible near-term training use of this simulator,
  precisely because the ground truth backing the label is unusually
  strong (mechanically checked, not merely asserted).
- **Reinforcement learning** — would need an agent making sequential
  decisions to *maximize* something, receiving a reward signal. No agent
  in `Simulation/` currently has an objective function at all (Working
  Section 5's honest gap — Person's behavior is a hand-tuned probability
  function, not a policy being optimized against any reward). Building
  an RL training loop today would mean either (a) training an RL policy
  to replace `spend_probability` against some invented reward (premature —
  there is no evidence the hand-specified rule is inadequate for anything
  the project currently needs it to do), or (b) training a *Heimdall-side*
  policy against simulated outcomes (blocked on Working Section 23's
  unbuilt bridge). Neither is ready.
- **Imitation learning** — would need real expert trajectories to imitate.
  `Simulation/` generates synthetic trajectories, not expert ones; this
  paradigm doesn't obviously apply to *generating* the world (though it
  could, someday, apply to training a Heimdall-side investigation policy
  against `financial_system/`'s own recorded human/system decisions — a
  different, unrelated question from simulation).
- **Offline learning / policy evaluation** — this is the paradigm this
  document judges most promising, and least built: `Simulation/`'s
  reproducibility discipline (Working Section 27) already makes it
  possible, in principle, to generate a large, fixed batch of world
  trajectories once, then evaluate many candidate policies against that
  same fixed batch without re-running the simulator per policy — exactly
  offline policy evaluation's precondition. Nothing currently consumes
  `Simulation/`'s output this way, but the output format (a complete,
  replayable event log) is already the right shape for it.

**[DESIGN OPINION]**, stated plainly because the research prompt asks
explicitly not to default to RL: nothing in `Simulation/` today has hit a
ceiling that a learned policy would clear and a hand-specified rule
cannot. The project's own measured finding (Working Section 1) is that a
small number of hand-specified, fully inspectable rules already produce a
real, non-trivial, verifiable causal structure. Introducing a learned
component anywhere in the *world-generation* loop would trade that
inspectability for a capability nothing currently needs — which is exactly
`Simulation/docs/Rules.md` #1's stated reasoning, re-confirmed rather than
merely repeated by this section's analysis.

## Working Section 25 — Build the Financial Simulation Laboratory

**[NOT BUILT]** as a system, but the shape of the research prompt's
example ("1000 worlds → Policy A → 1000 outcomes" vs. "...→ Policy B →
1000 outcomes → compare") maps directly onto a real, if manual, question
`Simulation/`'s own docs already pose without answering: `Memory.md`'s
open question "Whether Organization revenue should become a
periodic/ongoing stream (rather than a one-time world-generation lump
sum)" is precisely a Policy-A-vs-Policy-B question (today's lump-sum
funding vs. a periodic stream) that a laboratory harness would let someone
actually answer with numbers (does periodic funding produce a
meaningfully different payroll-failure rate?) rather than leave as an open
question in a markdown file.

What a real laboratory needs, concretely, beyond what exists: an
`Experiment` object bundling world configuration + population + mechanism
version + policy + intervention + seed list (today, none of these except
world configuration and seed are separate, nameable things — Working
Section 15's gap restated); a batch-run harness that runs N seeds per
configuration automatically (today's cross-seed checks, per Working
Section 17, were done by hand, three times, then the throwaway output
directories were deleted); and an outcome-comparison layer computing the
research prompt's named metrics (loss, fraud, false positives, liquidity,
customer impact, institutional stability, economic utility) — of these,
only "liquidity"-adjacent metrics (failure rate, balance distributions)
have any implementation today (`stats/report.py`, `validation/report.py`);
fraud, false positives, and institutional stability have no mechanism to
measure yet because the underlying phenomena (Working Sections 8, 26) are
themselves unbuilt.

## Working Section 26 — Build Adversarial Simulation

**[NOT BUILT]**, and honestly, not yet buildable in the research prompt's
full sense — an adversarial search loop needs a Heimdall (or Heimdall-like
system) to search *against*, and Working Section 23 already establishes
that no live bridge between `Simulation/` and `financial_system/` exists.
What can be said accurately today: `Simulation/`'s own validation system
already performs a narrow, one-shot version of the *diagnostic* half of
this loop (generate output → check whether it violates an expectation →
report where it does) without the *search* half (there is no loop that
mutates the world configuration to specifically look for a configuration
that breaks a check — `validation/report.py` reports GAP on the
spend/income-ratio check for the world configuration it was given; nothing
searches for a *worse* configuration to see how bad the gap could get).

The research prompt's own diagram is worth taking literally as a design
target for a future build, not for this document to attempt: `SIMULATOR →
GENERATE WORLD → HEIMDALL → FAILURE? → ADVERSARIAL SEARCH → HARDER WORLD →
HEIMDALL`. Every arrow in that loop requires a component this document has
already flagged as unbuilt (the observation bridge, a live Heimdall
connection, and — the genuinely new piece — a search/optimization
procedure over world configurations, which needs the Monte Carlo sampling
infrastructure of Working Section 17 as its substrate, likely with a
directed search strategy rather than uniform random sampling once a
specific failure mode is being targeted). This is squarely
`NORTH_STAR.md` §25's "Systemic Change #23," correctly still fully
aspirational there and here.

## Working Section 27 — Build Reproducibility

**[BUILT, and tested, for the fields it currently applies to]** — this is
the strongest-verified capability in the entire `Simulation/` project, and
worth being specific about exactly what "same seed = same world" has
actually been shown to mean, not just claimed:

- `Simulation/docs/Rules.md` #6 states the requirement.
- `tests/test_engine.py`'s determinism tests check it two ways: in-memory
  object equality across two runs with the same seed, *and*
  `filecmp.cmp`-verified byte-identical CSV output.
- Every phase's `Memory.md` section repeats a **manual, CLI-level**
  re-verification beyond pytest — e.g. Phase 2.5's: "ran
  `run_simulation.py --seed 42 --population 200 --days 60` twice into
  separate directories, `diff -rq` between them — zero differences across
  all 10 output CSVs... exit code 0."
- The mechanism behind this guarantee is named, not assumed: "exactly
  one `random.Random(seed)` instance exists per run... Entities are
  iterated in a fixed, seed-independent order (creation order) every
  tick" (`engine.py` docstring) — determinism is a structural property of
  the code's design, not an emergent coincidence that happens to hold.

**What the research prompt's fuller reproducibility record needs, that
`Simulation/` does not yet track as first-class fields**: `world_id`
(today, a run has no persisted identifier beyond its output directory
name — reproducibility is achieved, but not *indexed*), `mechanism_versions`
and `policy_versions` (no such objects exist to version, per Working
Section 15's gap), and `research_sources` (exists today, but as prose in
`Research.md`, not as a structured field attached to a specific run's
metadata). **[DESIGN OPINION]**: this gap matters more than it might first
appear, because the research prompt's actual reproducibility claim
("same seed + same configuration + same versions = same world") is
currently only checkable for the two fields `Simulation/` tracks
explicitly (seed, and the handful of CLI parameters) — code changes to
`person.py`'s constants between two runs at the same seed would silently
break reproducibility today with no mechanism-version field to flag that
the two runs are not actually comparable. This has not caused a real
problem yet only because every phase to date has been small enough for a
human to track by hand (`Memory.md`'s "Provenance of every
probability/rule" tables) — it would not scale past a few more phases
without becoming a real, versioned object.

## Working Section 28 — Define the Simulator's Epistemic Boundary

`Simulation/docs/Rules.md` #2's three-way label (research-grounded /
modeling assumption / placeholder) is a real, working, narrower instance
of the research prompt's seven-way scale (EMPIRICALLY OBSERVED / RESEARCH
SUPPORTED / CALIBRATED / INFERRED / PLAUSIBLE / ASSUMED / HYPOTHETICAL).
Mapping the two, and testing where the narrower scheme already in use
loses information the fuller one would keep:

| Research prompt's label | Nearest `Rules.md` #2 equivalent | Example, cited |
|---|---|---|
| EMPIRICALLY OBSERVED | *(no exact equivalent — nothing in `Simulation/` claims a full empirical calibration of a value, only of a shape/qualitative fact)* | closest: the BLS spend/income-ratio *pattern itself* (Research.md Part A §1) is empirically observed, but the simulator does not reproduce it — a case where the *research finding* is empirically observed even though the *mechanism* is not |
| RESEARCH SUPPORTED | "Research-grounded" | settlement delay's *qualitative* 1-3 day range (Stripe, cited) — `_run_settlement` docstring |
| CALIBRATED | *(no exact equivalent)* | nothing in `Simulation/` has been calibrated in the "re-fit against real data to minimize an error metric" sense yet — every parameter is either research-grounded for its *shape* only, or a named assumption |
| INFERRED | *(no exact equivalent)* | — |
| PLAUSIBLE | "Modeling assumption" | `SAVINGS_SWEEP_FRACTION = 0.15`, "loosely motivated by the common personal-finance... guideline... NOT independently verified" |
| ASSUMED | "Modeling assumption" | `HOUSEHOLD_SIZE_WEIGHTS`, "an honestly-labeled, uncited guess" |
| HYPOTHETICAL | "Placeholder" | `MERCHANT_CATEGORIES`, "a cosmetic label only" |

**Where the narrower scheme genuinely loses information**: `Rules.md`'s
"modeling assumption" bucket currently collapses two importantly different
things — a *loosely research-motivated* choice (`SAVINGS_SWEEP_FRACTION`,
motivated by a named real budgeting guideline, though not independently
verified) and a *pure, unmotivated guess* (`HOUSEHOLD_SIZE_WEIGHTS`, "not
derived from any real geographic/community-size data" — no guideline cited
at all). The research prompt's fuller scale (PLAUSIBLE vs. ASSUMED) would
keep this distinction visible where the current three-way label flattens
it. **[DESIGN OPINION]**: adopting the fuller scale is a low-cost,
genuinely useful refinement for any future phase — it requires no code
change, only a documentation-discipline change, and it directly serves
this document's own stated purpose (never letting SIMULATED silently
become REAL) by making the *degree* of groundedness visible at a finer
grain than the current scheme allows.

**The rule this whole section exists to protect, restated and tested**:
"Synthetic evidence cannot silently become empirical evidence"
(`NORTH_STAR.md` §33). `Simulation/`'s clearest test of this rule under
real pressure remains `Research.md`'s `sigma≈0.5` near-match — a number
that *looked* like independent confirmation of an existing constant and
was deliberately not treated as such. That is this rule working, not this
rule being stated.

## Working Section 29 — Determine the Minimum Viable World

**This is not a hypothetical question — it has already been answered, in
code, and run.** `Simulation/` Phase 1 is, concretely, almost exactly the
minimum world the research prompt's own worked example proposes:
Person, Account (the concrete form "Bank" takes), Merchant, Payment
(`Transaction`), Income (`salary`), Expense (`purchase`), Balance
(`Account.balance`) — with agents (Person/Bank/Merchant), events
(`Transaction`/`Event`), state (`Account.balance`, derived from `ledger`),
relationships (`Account.owner_id`), probabilities
(`spend_probability`/`purchase_amount`), and constraints (the
no-negative-balance check) all genuinely present, per
`Simulation/docs/Architecture.md`'s Phase 1 data model and
`Simulation/docs/Memory.md`'s "What exists" section.

And it already demonstrated the specific non-trivial emergent phenomenon
the research prompt's own example names: `income → liquidity → spending →
merchant revenue → bank balances`, with the `spending → failure` link
specifically *measured*, not merely claimed possible (Working Section 1's
citation of the balance-ratio table).

**Precisely where the real build differs from what an abstract analysis
(one not grounded in what already exists) might have proposed instead** —
this is the more valuable comparison, per this document's own instruction:

1. **No explicit "Payment" entity separate from Transaction.** An abstract
   minimum-viable-world analysis, following the research prompt's own
   entity list literally, might propose Payment as a distinct object from
   the underlying money-movement event (a Payment *initiates*, then
   *resolves into* a Transaction, mirroring `NORTH_STAR.md` §4's
   `PaymentInitiated → AuthorizationSucceeded → ...` event chain). The
   real Phase 1 build collapsed these into one `Transaction` row
   (`kind="purchase"` or `"payment_failure"`) with a single, atomic
   success/failure outcome per attempt — simpler, and sufficient for what
   Phase 1 needed to prove, but it means there is no room today for a
   payment's *own* multi-step lifecycle (authorize, then separately
   capture) without a real schema change, not just a new `kind` value.
2. **No explicit "Merchant" behavior at all**, where an abstract minimum
   world balancing "Person" and "Merchant" symmetrically might have given
   the Merchant *some* minimal decision (even just "attempt to restock" or
   "vary price slightly") to make it a peer agent rather than a passive
   money sink. The real build deliberately kept Merchant fully passive
   (`merchant.py`'s own docstring: "Merchants still have no spending
   behavior of their own") — the right call for testing the specific
   hypothesis Phase 1 existed to test (does a Person's own state causally
   drive Person-side outcomes), but it means the "merchant revenue"
   half of the example emergent chain is present only as a passive sum,
   never as a Merchant *decision* responding to that revenue.
3. **Bank was built richer, sooner, than a strict "minimum" would require.**
   The research prompt's own minimum-world example lists "Account," not
   "Bank" with a real double-entry ledger — an abstract minimum-viable
   analysis could plausibly have gotten away with a single scalar balance
   per account and no separate institutional ledger at all for a first
   proof of the causal hypothesis. The real project instead built genuine
   double-entry bookkeeping starting in Phase 2 (immediately after Phase
   1's minimum proof succeeded), which turned out to be a good decision
   in hindsight — it is what made Organization's real, traceable payroll
   mechanism (Working Section 7) possible in Phase 2.5 — but it is
   *more* institutional depth than a strict "minimum" reading of the
   research prompt's own example would have required at that stage.
4. **The real build discovered a genuine, load-bearing confound (balance
   ratio vs. income level, Working Section 1) that a purely abstract
   design exercise could not have predicted** — this is arguably the
   single most important difference: an abstract minimum-viable-world
   analysis can specify *that* a causal mechanism should exist, but only
   an actually-run simulation can reveal *which* specific variable
   combination carries the signal versus which merely looks like it
   should. This is, in miniature, the entire justification for building
   real simulations instead of only reasoning about what a simulation
   should contain — a point this document's own existence should not be
   allowed to obscure by being 33 sections of reasoning about a system
   whose most valuable finding required actually running it.

## Working Section 30 — Then Expand Recursively

`Simulation/docs/Phases.md`'s own phase list is already the concrete,
scoped version of the research prompt's expansion diagram — worth reading
side by side rather than re-deriving a new one:

```
Research prompt's diagram:          Simulation/docs/Phases.md's actual scope:

PAYMENTS                            Phase 1/2/2.5 -- DONE (purchase,
                                     salary, settlement, all built)
   ↓
CREDIT                              Phase 3+/Beyond-Phase-6 -- Research.md
                                     Part C.2/C.3 groundwork exists, NOT
                                     BUILT
   ↓
FRAUD                                Research.md Part C.1 groundwork
                                     exists, NOT BUILT
   ↓
AML                                   Not researched, not built, no
                                     groundwork at all yet
   ↓
SETTLEMENT                            Phase 2 -- DONE (merchant pending
                                     -> settled, T+1)
   ↓
ACCOUNTING                            Phase 2 -- DONE (double-entry
                                     ledger)
   ↓
TREASURY                              Partially present (bank_reserve
                                     asset account) but no active
                                     liquidity-management decision --
                                     Working Section 7
   ↓
INSURANCE                             Not researched, not built
   ↓
MARKETS                               Not researched, not built
```

The real project's phase ordering does not match the research prompt's
proposed ordering exactly, and that mismatch is itself informative: the
real build did Accounting and Settlement *before* Credit or Fraud, not
after — because, per `Phases.md`'s own Phase 2 rationale, a real ledger
was judged to be a *prerequisite* infrastructure layer (every later
domain needs a place to post its money movements) rather than a peer
domain to sequence alongside Payments/Credit/Fraud. **[DESIGN OPINION]**,
consistent with `NORTH_STAR.md` §26's "Domain Package Architecture": this
was the right call, and it validates the research prompt's own §30
principle ("Each new domain should reuse: world model, event model...")
more concretely than an abstract statement of the principle could — Credit
and Fraud, whenever built, will need exactly the ledger, event, and
account infrastructure Phase 2 already built and proved, not a
domain-specific one of their own. `Research.md` Part C's own "why not
built now" reasoning for all three proposed domains (fraud, credit, loans)
independently arrives at the same conclusion from the opposite direction:
each proposal's blocker is precisely "this needs [ledger-adjacent
infrastructure] Phase 2's design never addressed," not "this domain is
conceptually unclear."

## Working Section 31 — Final Simulation Architecture (Component Overview)

This working section previews, at a component level, what Part II below
specifies in full. For each of the research prompt's 17 named components:
purpose, and current status against `Simulation/`.

| Component | Purpose | Status |
|---|---|---|
| World Model | Canonical ontology + registry of entities/relationships | **[PARTIALLY BUILT]** — `world/models.py`'s dataclasses; no registry/graph layer |
| Event Engine | Append-only, causally-ordered event log | **[BUILT]** — `Event`, `_record()` |
| State Engine | Project state from event history | **[BUILT]** — `Account.balance` reconstructable from `ledger` |
| Agent Engine | Per-agent decision functions over own state | **[BUILT]** — `Person.spend_probability` et al. |
| Institution Engine | Internal institutional systems (ledger, treasury, risk...) | **[PARTIALLY BUILT]** — ledger + settlement only, per Working Section 7 |
| Behavior Engine | `P(action \| state)` computation across agent types | **[BUILT, one agent type]** — Person only; Bank/Merchant have no probabilistic behavior |
| Economic Engine | Mechanisms connecting state/events to economic outcomes | **[PARTIALLY BUILT]** — liquidity constraint only, per Working Section 8 |
| Network Engine | Relationship-graph structure and its influence on behavior | **[STRUCTURE BUILT, INFLUENCE NOT BUILT]** — per Working Section 13 |
| Mechanism Engine | Versioned, swappable mechanism objects | **[NOT BUILT]** — mechanisms are constants+functions in source, not first-class objects |
| Scenario Engine | Configure and launch a named scenario type | **[NOT BUILT]** — one scenario type (baseline) only, per Working Section 15 |
| Counterfactual Engine | Branch a world at time t | **[NOT BUILT]** — per Working Section 16 |
| Sampling Engine | Draw many worlds from a configuration distribution | **[NOT BUILT, informally proven cheap]** — per Working Section 17 |
| Observation Engine | Construct observer-scoped, time-bounded views | **[NOT BUILT]** — the single highest-leverage gap, per Working Section 18 |
| Calibration Engine | Fit parameters against real data | **[NOT BUILT AS A LOOP; ONE MANUAL PASS DONE]** — per Working Section 20 |
| Validation Engine | Multi-level checks against internal consistency and reality | **[BUILT, narrow but real]** — `validation/` package, per Working Section 21 |
| Experiment Engine | Bundle + run + compare named experiments | **[NOT BUILT]** — per Working Section 25 |
| Reproducibility Engine | Deterministic replay given seed+config+versions | **[BUILT for tracked fields; versioning objects don't exist yet]** — per Working Section 27 |

Full purpose/inputs/outputs/dependencies/mathematical-foundations/
failure-modes detail for each of these appears in Part II below, organized
by the deliverable's own 30-item structure rather than repeated here.

## Working Section 32 — What Should NOT Be Built Yet

Classifying every capability discussed above, per the research prompt's
own six-way scheme. This section is deliberately short on the
"BUILD NOW" side — the discipline this whole document tries to hold,
matching `docs/FUTURE_ARCHITECTURE.md`'s own stated reasoning for why its
four upgrades aren't being built for the current submission either.

**BUILD NOW** — genuinely small, low-risk, and immediately useful,
none touching a frozen/tested invariant:
- Nothing. This document is long-term vision, exactly like
  `NORTH_STAR.md`, produced explicitly as design/research writing, not as
  a task list for the current session. Recommending even a "small" build
  here would be exactly the scope creep this repository's own
  memory file (`feedback_scope_creep_pushback.md`, referenced in this
  session's own context) flags as a recurring, correctly-pushed-back-on
  pattern. If a genuinely small next step is wanted, Working Section 30's
  observation on ordering (infrastructure before domains) and Working
  Section 13's "extract the existing implicit payment network from
  current output" (a read-only analysis over already-written CSVs, no
  simulation-loop change) are the two lowest-risk candidates named
  anywhere in this document — named, not recommended for immediate action.

**BUILD AFTER FOUNDATION** (i.e., after the Observation Engine, Mechanism
Engine, and Scenario Engine gaps are closed — everything below depends on
at least one of those three):
- Counterfactual Engine (Working Section 16) — needs Mechanism/Scenario
  versioning to know what varies between branches, and needs the
  per-agent-RNG-stream design question resolved first.
- Sampling Engine as an automated system (Working Section 17) — the
  underlying capability is cheap; the automation harness is not built.
- Experiment/Laboratory Engine (Working Section 25) — needs Scenario
  Engine as its substrate.
- Calibration loop, as a loop rather than a one-time pass (Working
  Section 20).

**RESEARCH FIRST** (a design decision genuinely needs more thought before
any code, independent of engineering effort):
- The counterfactual RNG-isolation question (Working Section 16) —
  per-agent seeding vs. a strict draw-count invariant is a real design
  fork with different tradeoffs, not yet resolved even on paper.
- Whether/how Household/Organization/Community should ever influence
  agent behavior (Working Section 13) — `Community`'s own docstring
  already states this is deliberately undecided, not merely unbuilt.

**REQUIRES EMPIRICAL DATA** (a mechanism this document can specify but
cannot honestly calibrate without new research, per `Rules.md` #2/#5):
- The income-level-dependent spend-fraction fix (Working Section 8) — the
  *qualitative* direction is real and cited (BLS CE), but no clean
  functional form has been found yet (`Research.md` Part A §1's own
  stated gap).
- `BASE_DAILY_SPEND_PROB`'s real-world anchor (the DCPC lead, blocked on
  this session's PDF-extraction tooling limitation, per `Research.md`).

**REQUIRES EXTERNAL VALIDATION** (needs comparison against real
institutional behavior this project has no access to):
- Any Institution Engine expansion beyond ledger/settlement (Working
  Section 7) — a bank's real risk/AML/compliance behavior is not the kind
  of thing publicly summarized statistics can calibrate; it would need
  either a cooperating institution or a materially different research
  approach than `Research.md`'s public-statistics method.

**EXPERIMENTAL** (worth trying specifically to learn whether it's viable,
not because its value is already established):
- Offline policy evaluation against `Simulation/`'s existing output
  format (Working Section 24) — the one training paradigm this document
  judges plausibly ready, but untested.

**NOT CURRENTLY JUSTIFIED**:
- Any learned/ML policy replacing a hand-specified behavioral rule
  (Working Section 24) — nothing has hit a ceiling a learned policy would
  clear.
- An LLM anywhere in the simulation loop itself (`Rules.md` #1, reaffirmed
  by this document's own analysis in Working Section 5, not merely
  repeated from the rule).
- Markets domain (no groundwork of any kind exists; premature relative to
  Credit/Fraud/AML, which at least have `Research.md` Part C groundwork).
- Adversarial Simulation (Working Section 26) — has no Heimdall bridge to
  search against yet; building the search mechanism before its target
  exists would be building for a connection that doesn't exist.

## Working Section 33 — Pointer to the Deliverable

The complete, final Simulation Architecture Specification — matching this
research prompt's own item 33, its 30-part table of contents — follows
below as Part II. Part I above is the reasoning that produced it; Part II
is the specification itself, synthesized rather than re-derived, with
every claim still traceable back to a Working Section above or to a named
file/citation.

---

# PART II — Simulation Architecture Specification for Heimdall

*(This is the deliverable proper — the research prompt's own item 33.
Each item below is deliberately more compact than its Part I counterpart:
it states the specification, its build status, and a pointer back to the
Working Section carrying the full reasoning and citations, rather than
re-arguing the case.)*

## 1. Definition of a Financial World

A financial world is a set of entities with persistent state, connected
by relationships and constraints, whose state changes only through
discrete, causally-ordered events, where each event's probability or
occurrence is a function of the state of the entities involved. A
transaction log is an observable projection of a world, never the world
itself. **Status**: this definition is not aspirational — `Simulation/`
is a working instance of it (Working Section 1), and the project's
central finding (a measured, monotonic balance-ratio → failure-rate curve
across three seeds, `Simulation/docs/Memory.md`) is direct evidence the
definition has real teeth, not just conceptual appeal.

## 2. World Ontology

Nine categories (ENTITY, EVENT, STATE, RELATIONSHIP, CONTRACT, OBLIGATION,
RESOURCE, POLICY, MECHANISM). Five are built today (ENTITY, EVENT, STATE,
RELATIONSHIP, MECHANISM, as concrete dataclasses/functions in
`Simulation/world/models.py` and `world/agents/*.py`); four are not
(CONTRACT, OBLIGATION, POLICY as first-class objects, and RESOURCE beyond
money). CONTRACT/OBLIGATION are the highest-leverage gap — nearly every
named future domain (Credit, Insurance, Settlement obligations) is a
Contract/Obligation instance, per Working Section 2. ENTITY/EVENT/STATE/
RELATIONSHIP are universal, shared infrastructure; POLICY/MECHANISM are
universal *shape*, domain-owned *content*; CONTRACT/OBLIGATION are
universal shape, domain-specific terms — a shared base class per domain
package, not one undifferentiated Contract type (`NORTH_STAR.md` §26).

## 3. Entity Model

Built: `Person`, `Bank`/`Account`, `Merchant`, `Household`, `Organization`,
`Community` (`Simulation/world/models.py`). Each entity's owned
resources, available actions, maintained state, relationships, possible
events, and constraints are fully enumerated in Working Sections 2 and 5,
per entity. `Person` is the only entity with genuine probabilistic
decision-making; `Household`/`Organization`/`Community` are structural
groupings with real ledger-backed accounts but zero decision logic of
their own (`world/models.py`'s own docstrings for each, per Working
Section 13) — a deliberate, stated design choice (`Architecture.md`'s
"only Person/Bank/Merchant carry probabilistic decision logic"), not an
oversight. Regulator, Government, Central Bank, Fund, Insurer
(`NORTH_STAR.md` §3's fuller list) do not exist in any form.

## 4. Event Model

Built: append-only `Event` + `Transaction` pair per economic movement,
`event_type`/`kind` taxonomy currently covering
`salary`/`purchase`/`payment_failure`/`settlement`/`savings_sweep`/
`household_sweep`/`org_funding` (`world/models.py`, `world/engine.py`).
Every event carries actor, target, timestamp, and (via `balance_before`) a
direct, checkable trace of its cause — Working Section 4's per-attribute
table. The world is event-first by design: state is always a projection
of event history, never independently mutated (`bank.py`'s `_post()`).
Not built: the fuller event taxonomy `NORTH_STAR.md` §4 names
(`AuthorizationSucceeded`, `RefundIssued`, `ChargebackOpened`,
`LoanIssued`, etc.) — each requires domain machinery (Working Section 30)
that doesn't exist yet.

## 5. State Model

`State(t+1) = Transition(State(t), Event(t))`, implemented literally in
`Bank._post()` — a state and its producing event are always written
together, never separately (Working Section 3). State is classified into
persistent/derived/temporary/historical/latent/observable; today,
"observable" collapses onto "everything the simulator ever computed" —
there is no notion of a restricted, observer-specific view. This is the
single largest state-model gap and is the same gap named in item 15
below.

## 6. Agent Model

Built: a genuine `state → probability → event` pipeline for one agent
type (Person), with every constant provenance-labeled
(`Simulation/docs/Rules.md` #2, `person.py`). Objectives, information, and
beliefs are honestly absent — Person's behavior is a hand-tuned
probability function, not a utility-maximizing policy (Working Section 5).
Techniques suited to different behaviors are mapped in Working Section 5's
table: rules and conditional-probability functions are proven in
production use; Markov processes, utility functions, game theory, and
network models are each named as the right fit for a specific
not-yet-built behavior, with the specific trigger condition for adopting
each named rather than left vague. LLMs are deliberately excluded from
every cell of that table, consistent with `Simulation/docs/Rules.md` #1.

## 7. Institution Model

Built: Bank's Account registry and real double-entry Ledger
(`world/agents/bank.py`), Merchant's pending→settled settlement state
machine (`world/agents/merchant.py`, `engine.py`'s `_run_settlement`),
Organization's real, traceable, ledger-backed payroll with a genuinely
reachable failure path (`Memory.md`'s Phase 2.5 section). Not built: Risk,
Fraud, AML, Compliance, active Treasury/liquidity management, or any
Policy object for any institution (Working Section 7's full table).
Institutional-policy-driven cascading behavior (`NORTH_STAR.md` §7's
worked example) has no substrate to attach to today, because no Policy
object exists anywhere to vary.

## 8. Behavioral Model

`P(action | state, incentives, constraints)`, built and measured for one
behavior (Person's daily purchase attempt, Working Section 6). The one
genuine emergent correlated-behavior chain this simulator has actually
produced end-to-end and measured (not merely designed for) is: lower
balance → lower attempt probability → higher failure probability given an
attempt, with a documented, honest confound finding (balance ratio, not
income level, carries the signal) that the codebase discovered by running,
not by design. Extending this chain toward "credit deterioration" and
"future borrowing constraints" is fully specified as a proposal in
`Simulation/docs/Research.md` Part C.2/C.3, cited with real numbers, but
not implemented — blocked on new persistent, non-ledger-reconciled agent
state (credit score) that Phase 2's ledger-invariant discipline was never
designed to hold.

## 9. Economic Mechanisms

One mechanism fully built and measured (liquidity constraint on spending).
Several more have real, cited research groundwork but zero implementation
(fraud rate targets, credit delinquency-transition targets, loan-pricing
structure — all `Research.md` Part A/C, Working Section 8). Several are
neither built nor researched (bank runs, market formation, inflation,
unemployment) and this document explicitly does not recommend building
them before the underlying micro-mechanisms (pricing, employment linkage)
they'd need to be emergent from (Working Section 22) exist. One genuinely
useful *negative* finding is worth keeping visible in any future lending
design: reserve-requirement-style capital constraints would be
factually anachronistic for a present-day-set simulation (Fed reserve
ratios have been 0% since March 2020, `Research.md` Part A §5) — a
Basel/LCR-style capital-adequacy constraint is the correct model to reach
for instead, not the intuitive-seeming default.

## 10. Network Model

Real relationship structures exist (Household, Organization, Community —
all genuinely linked, none currently influencing behavior, Working
Section 13). The simulator's own output already implicitly contains an
unextracted payment network (every `Transaction.from_id → to_id` edge).
No fraud/AML/contagion/systemic-risk mechanism reads any network structure
today. This is named as the clearest example in this entire document of
"the data structure exists; the causal mechanism built on top of it does
not" — a distinction worth holding onto for anyone tempted to treat
`Household`/`Organization`'s existence as evidence that network effects
are already modeled.

## 11. World-Generation Pipeline

Built and working: `SimulationEngine._build_world` implements a real,
ordered, dependency-aware pipeline (institutions before population;
opening balance drawn as a function of a person's own income, not
independently; Organization funding computed only after every employee's
income is known — Working Section 11). Cross-person correlation (household
income correlation, geography) is explicitly and honestly not modeled —
population generation is i.i.d. per person, named as a real gap in
`Simulation/docs/Memory.md` itself, not discovered by this document.

## 12. World-Evolution Pipeline

Built: a full, tested, deterministic time-stepped day loop implementing
the research prompt's abstract pipeline concretely (Working Section 12).
Time-stepped, day-granular simulation is a reasoned choice — it matches
the actual cadence of every phenomenon currently modeled (daily
settlement batches, daily behavioral decisions) — not a default; the
concrete trigger condition for needing a general discrete-event queue
instead (sub-day-granular phenomena like authorization-then-capture, or
intraday liquidity) is named but has not yet been reached by anything in
this codebase. Causal ordering within a tick and across a run is
guaranteed by two structural properties, not by convention: a single
seeded RNG stream and fixed creation-order iteration, both stated as hard
requirements in `engine.py`'s own module docstring.

## 13. Research-to-Mechanism Pipeline

A real, working, if manual, instance exists (Working Section 9): PAPER →
CLAIM → FORMALIZATION → SIMULATION COMPONENT → CALIBRATION → VALIDATION,
walked concretely through the settlement-delay example, with every field
the research prompt asks a mechanism record to carry (source, claim,
formalization, assumptions, parameters, parameter source, calibration,
uncertainty, validity range, limitations) genuinely present, if currently
scattered across a docstring and a markdown file rather than structured
as one object. What's missing is automation — the "DISCOVERY.AI" role in
this pipeline was a human-directed research session, not an autonomous
system; and structure — this record needs to become machine-readable
per mechanism, not prose, before it can be queried or audited at scale
(`NORTH_STAR.md` §34's "Research Provenance System," fully aspirational
still).

## 14. Calibration Methodology

One real calibration pass completed and documented in full
(`Research.md` Part B): four parameters evaluated against real published
statistics, one changed (a provenance label, deliberately not a value),
three explicitly rejected with stated reasons. This is evidence the
methodology (compare, then adopt only what is both clean and cleanly
mapped) works under real pressure, not just as a stated intention — the
`sigma≈0.5` near-match rejection (Working Section 9) is the sharpest test
case. A calibration *loop* (automatic re-fitting against a scored
objective, iterated) does not exist — today's calibration is a single,
careful, human-read pass, not an automated procedure, and would need the
Monte Carlo sampling infrastructure (item 19) as its substrate to become
one.

## 15. Observation Boundaries

**Not built — the single highest-leverage gap this entire specification
identifies.** Today, everything the simulator computes is, by
construction, visible in its output; there is no `WorldSnapshot(as_of,
observer, scope)` primitive (`NORTH_STAR.md` §5) distinguishing
simulator-internal ground truth from what a given observer, at a given
simulated time, would actually have known. `financial_system/`'s real,
tested Risk temporal-leakage fix (Block 5) is the working proof this
principle is buildable and valuable in one domain already —
`Simulation/` has not yet generalized it. Building this is a precondition
for making ground truth (item 16) usable as ground truth rather than as
the only available view, and for any honest future connection to Heimdall
(item 25) — described in Working Section 18, not designed further here.

## 16. Ground-Truth Model

Structurally present, not yet exploited as a distinct capability: every
simulated causal claim is, today, machine-checkably true — a
`payment_failure`'s cause is asserted by the engine and independently
verified by tests and by `validation/`'s runtime checks
(`tests/test_engine.py`, `validation/report.py`'s
`check_causal_balance_ratio`) — a property no real transaction dataset
can have. This becomes usable as *ground truth distinct from observation*
only once item 15 exists; until then, ground truth and observation are
the same object, which makes any evaluation against today's output
implicitly leak information a real intelligence system would never have
had (Working Section 19).

## 17. Scenario Generation

One scenario type (BASELINE, parameterized by population/duration/seed)
is fully built via `run_simulation.py`'s CLI. The other six named types
(CALIBRATED, STRESS, ADVERSARIAL, COUNTERFACTUAL, HISTORICAL,
HYPOTHETICAL) each require infrastructure this specification lists as
not yet built (a calibration loop, a shock layer, an adversarial search
loop, a branching mechanism, real historical-regime data, and a
versioned Mechanism/Policy axis to vary respectively) — mapped in full in
Working Section 15's table. The single biggest structural blocker shared
across most of these: mechanisms and policies are currently constants and
functions baked into source files, not swappable, versioned, first-class
objects a scenario could select among.

## 18. Counterfactual Worlds

Not built. `Simulation/`'s determinism guarantee (item 22) makes branching
at time `t` cheap *in principle* (replay identically to `t`, then diverge),
but surfaces one genuine, unresolved architectural question worth carrying
forward rather than glossing over: the project's single shared
`random.Random(seed)` stream has no per-agent isolation, so an
intervention that changes how many RNG draws one agent consumes would
silently perturb every other, unrelated agent's subsequent draws too
(Working Section 16). Resolving this — per-agent-seeded RNG streams, or a
strict no-draw-count-change invariant on interventions — is a prerequisite
design decision, not an implementation detail, for building this
component honestly.

## 19. Monte Carlo Sampling

The underlying capability is cheap and already informally proven:
`Simulation/docs/Memory.md`'s own cross-seed robustness check
(seed=7/2026, re-confirming the balance-ratio finding) is a real, if
manual and one-off, instance of exactly this — many worlds from a
distribution (here, only the seed varies; the configuration does not),
compared, and reported. No automated harness exists to sweep configuration
parameters the same way seed already varies, no scored aggregation
exists beyond a hand-built table, and rare-event/importance sampling
(e.g. deliberately searching for a world where the deliberately-rare
Organization payroll failure actually fires) has no design yet at all.

## 20. Adversarial Worlds

Not built, and not yet fully buildable: an adversarial search loop needs
a live target to search against, and no bridge to `financial_system/`
exists (item 25) — nor should one, per `Simulation/docs/Rules.md` #4 and
`Phases.md` Phase 6, which this specification does not propose overriding.
`validation/`'s existing GAP-detection (spend/income-ratio check) is the
diagnostic half of this loop already present in miniature, with no search
half attached.

## 21. Training Environment

`Simulation/`'s output format (a complete, replayable, deterministic event
log) is already the right shape for offline policy evaluation — this
document's own judgment (Working Section 24) is that this is the single
most defensible near-term training use, precisely because it requires no
new simulation-loop machinery, only a consumer reading existing output.
Supervised learning against the verified `payment_failure` label is a
close second, for the same reason (the label's cause is mechanically
checked, not merely asserted). Reinforcement learning is explicitly judged
not yet justified: no agent has an objective function to optimize against,
and nothing currently modeled has hit a ceiling a learned policy would
clear that a hand-specified, fully inspectable rule cannot.

## 22. Evaluation Environment

`validation/`'s B.1/B.2 split (internal mechanism consistency vs.
comparison against `Research.md`'s real numbers) is a real, working,
multi-level evaluation system — covering micro, macro, and (narrowly)
meso and temporal levels, per Working Section 21's table, with one
documented near-miss (a false PASS from a too-loose threshold, caught and
fixed before shipping, `Memory.md`) as direct evidence the system has
actually been pressure-tested, not merely designed. Causal-level
evaluation is entirely blocked on the (unbuilt) Counterfactual Engine, and
network/topology-level evaluation is blocked on the (unbuilt) causal
network mechanisms in item 10.

## 23. Reproducibility Model

Built, tested, and re-verified at the CLI level on every phase to date —
the strongest-proven capability in the project (Working Section 27).
`world_id`, `mechanism_versions`, and `policy_versions` as first-class,
persisted fields do not exist yet, because mechanisms and policies are
not yet first-class objects (same gap as item 17) — today's
reproducibility is real but tracked only for the fields that already have
explicit identity (seed, the handful of CLI configuration parameters), a
gap that has not caused a real problem yet only because every phase so
far has been small enough to track by hand.

## 24. Verification Model

`Simulation/`'s own test suite (45 tests, `tests/test_engine.py` +
`test_ledger.py` + `test_phase25.py` + `test_validation.py`) already
verifies a real, if narrower, subset of `NORTH_STAR.md` §24's list:
"was the state correct" (double-entry invariant, no-negative-balance),
"can the decision be replayed" (determinism tests), "was the outcome
correct" (conservation checks — merchant settled+pending equals total
proceeds). "Was future information leaked" has no check today, because no
observation boundary exists yet to leak across (item 15) — this is the
one verification category this specification can name as entirely
unaddressable until that gap closes.

## 25. Integration with Heimdall

Deliberately not built, per `Simulation/docs/Rules.md` #4 and
`Phases.md` Phase 6 — this specification names what a future bridge would
require without proposing crossing the boundary now: an Observation
Engine (item 15) interposed before any Heimdall-side read; a way for
`financial_system/`'s Action layer to write an event into a *running*
Simulation world rather than only reading a finished export; and
`Simulation/`'s own retry mechanism (`Phases.md` Phase 4, not started),
since a Recovery decision to retry has nothing to act on without it
(Working Section 23's full pipeline diagram). `FUTURE_ARCHITECTURE.md`'s
four proposed Heimdall-side upgrades (shared investigation, compound
reasoning, computational uncertainty, outcome-driven re-evaluation) are
independent of this bridge and do not require it — they operate on
`financial_system/`'s real corpus regardless of whether a simulated world
is ever connected.

## 26. Integration with Discovery.AI

Fully aspirational — `NORTH_STAR.md` §8-9's proposed autonomous
research-to-mechanism pipeline has no implementation anywhere; what exists
instead (Working Section 9/13) is a human-directed research session
producing a written document a human then read before making one narrow,
cited change. The gap between the two is not merely "not automated yet" —
it is the difference between a documented *method* (search, verify, cite,
adopt-or-reject, write down why) and a *system* that could execute that
method against new sources without a human in the loop for each step.

## 27. Domain Expansion Architecture

`NORTH_STAR.md` §26's "domain package" pattern (Ontology, Entities,
Events, State, Relationships, Mechanisms, Policies, Actions, Evidence,
Evaluators, all layered on shared substrate) is validated, not just
proposed, by `Simulation/`'s own phase ordering: Accounting and Settlement
were built *before* any candidate domain (Credit, Fraud), specifically
because every later domain needs the ledger/event/account infrastructure
those phases established (Working Section 30). `Research.md` Part C's
three proposed-but-unbuilt domains (fraud, credit, loans) each name the
same blocker independently — new agent state or new ledger-adjacent
machinery Phase 2's design never addressed — which is itself evidence the
"build shared infrastructure before domains" ordering, chosen for Phase
1/2, generalizes correctly to future domains too, not just retrospectively
justifies the choices already made.

## 28. Minimum Viable World

Already built and run — not a proposal. `Simulation/` Phase 1 is, in
substance, the research prompt's own worked minimum-world example
(Person/Account/Merchant/Payment/Income/Expense/Balance), and it already
demonstrated its target non-trivial emergent phenomenon (income → liquidity
→ spending → failure), measured across three seeds. Section 29 (Part I)
gives the full, specific comparison between what was actually built and
what an abstract minimum-viable-world analysis, unconstrained by having
actually been run, might have proposed instead — four concrete
differences (no separate Payment lifecycle object, a deliberately passive
Merchant, a richer-than-strictly-minimal Bank ledger, and a discovered
confound no design exercise could have predicted), each with its own
tradeoff named honestly rather than treated as simply "more" or "less"
complete.

## 29. Long-Term Evolution Roadmap

Not a new roadmap — `Simulation/docs/Phases.md` already is one, and this
specification defers to it rather than duplicating it: Phase 1/2/2.5 done;
Phase 3 (behavioral realism) partially done (a real research pass
completed, one narrow cited change made, `Research.md`); Phase 4 (domain
events — retries, refunds) not started; Phase 5 (scale) not started; Phase
6 (Heimdall bridge) explicitly deferred as a future *decision*, not a
default; "Beyond Phase 6" (AML, credit, treasury, markets, the three-graph
architecture, model training) recorded as long-term direction only. This
specification's own contribution to that roadmap is Working Sections
9-27's more detailed reasoning about *what each of those future phases
would specifically require*, grounded in what already exists — not a
replacement roadmap, an elaboration of the existing one's later, currently
one-line entries.

## 30. Major Unresolved Research Questions

Named plainly, each carried forward from where it surfaced in Part I,
because leaving them as open questions is the honest outcome, not a
deferred TODO to be quietly resolved by assumption:

1. **The counterfactual-branching RNG-isolation design fork** (Working
   Section 16/18) — per-agent-seeded streams vs. a strict draw-count
   invariant — unresolved even on paper, and blocking for item 18.
2. **Whether relationship structure (Household/Organization/Community)
   should ever causally influence agent behavior**, and if so how — an
   explicitly, deliberately undecided question per the project owner's own
   framing (`Community`'s docstring), not merely unbuilt.
3. **What functional form should connect purchase size to income level**
   to close the one real, measured GAP this project has found
   (`validation/report.py`'s spend/income-ratio check) — the *direction*
   is real and cited (BLS CE), the *specific mechanism* is not yet
   designed even at the proposal stage.
4. **Whether a structured, machine-readable research-provenance object**
   (rather than prose scattered across docstrings and markdown) is worth
   building before or after Discovery.AI-style automation, given that the
   discipline already works manually — an ordering question, not a yes/no
   one.
5. **What the right unit of "calibration" is for a mechanism whose
   real-world analog is itself contested or thin** (e.g. fraud detection
   false-positive rates — `Research.md` Part A §2's own explicit finding
   that benchmark-dataset numbers are known-unrepresentative and therefore
   "not usable" for calibration) — this is a genuine open methodological
   question the research prompt's calibration framework does not, by
   itself, resolve.
6. **Whether offline policy evaluation (item 21) is actually a productive
   training paradigm for anything Heimdall-adjacent**, or merely
   *possible* given the output format — named as experimental in Working
   Section 32 specifically because this document has no evidence either
   way, only a structural argument that it's the least-blocked option.

---

*End of specification. Part I's Working Sections carry full citations and
reasoning for every claim summarized in Part II; nothing in Part II should
be read as adding a new claim beyond what Part I already established and
cited.*
