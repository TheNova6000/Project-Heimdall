# North Star: Heimdall as a Financial Intelligence Substrate

This document is the long-term vision behind this project, recorded in
full and verbatim, the same way `FUTURE_ARCHITECTURE.md` records the
near-term "next evolution" already scoped against this submission's
judging criteria. The two documents operate at different horizons:
`FUTURE_ARCHITECTURE.md` is the next deliberate step (four concrete
upgrades to Risk/Controller/Recovery's shared reasoning); this document
is the multi-year direction those steps, and the `Simulation/` project,
are both small early instances of.

**Nothing below is implemented.** It is not a roadmap for this
buildathon, and no part of it should be inferred as built from the
diagrams. It is recorded here — before being asked "what's next" — for
the same reason this repository already names every other deliberately
deferred piece: to show the vision was thought through, not omitted by
oversight.

## Already prefigured in this repository, today

Several of this document's core principles aren't purely aspirational —
they're generalizations of things already built, tested, and frozen
here, in miniature, in one domain at a time:

- **§5, temporal snapshots ("no intelligence component should silently
  see the future")** — this is exactly `financial_system/`'s Risk
  temporal-leakage fix (Block 5): every Risk decision is already pinned
  to what was knowable *at the time*, not global truth. The document's
  ask is to generalize that from one domain to a universal primitive.
- **§10, "the world should not require an LLM to generate every
  action... LLMs belong in reasoning and discovery, not as the physics
  engine of finance"** — this is `Simulation/docs/Rules.md` Rule #1,
  word for word in spirit, already enforced: the entire agent-based
  simulation is deterministic + probabilistic, zero LLM calls in the
  loop, verified by test on every phase.
- **§33–34, research provenance ("every simulation mechanism must carry
  source, evidence, assumptions... synthetic evidence cannot silently
  become empirical evidence")** — this is `Simulation/docs/Rules.md`
  Rule #2 (every rule labeled research-grounded/modeling-assumption/
  placeholder), concretely exercised in `Simulation/docs/Research.md`,
  which cites real Fed/BLS/FRED sources and — just as importantly —
  explicitly declines to adopt several tempting-looking numbers that
  failed verification, rather than quietly upgrading their provenance.
- **§9, §29–32, simulation as a reproducible, sample-able environment
  ("same seed + same configuration = same world"; "the unit of
  evaluation can become a world rather than a row")** — this is
  `Simulation/`'s determinism discipline (Rules.md #6, tested on every
  phase via byte-identical-output checks) plus the `validation/`
  package (Phase 2.5): it samples a completed run and reports both
  internal mechanism consistency and comparison against cited
  real-world numbers — a small, working instance of exactly the
  "sample worlds, compare to reality, report honestly" loop this
  document describes at full scale.
- **§10, entities list; §11, "institutions as computational systems"**
  — `Simulation/`'s Phase 2 (double-entry ledger, real Bank accounts)
  and Phase 2.5 (Household, Organization with a real ledger-backed
  revenue account, Community) are a first, small, honestly-scoped
  instance of exactly this: agents as the base unit, with institutional
  and social structure as abstraction layers over them, not new
  hardcoded entity types with their own decision logic.
- **§12–13, "replace synthetic dataset with simulated world"; "real
  datasets as calibration, not definition"** — this is `Simulation/`'s
  entire premise (`PRD.md`'s "Why": `financial_system`'s
  `retry_would_succeed` coin-flip has no causal structure) and
  `Research.md`'s method exactly: cited public statistics used to
  check and calibrate existing mechanisms, never bulk-downloaded to
  *define* them wholesale.
- **§16, "if the system cannot justify a term: UNKNOWN, it must not
  fabricate precision"** — this is `financial_system/`'s R0/EV wiring
  into the real action-execution loop, and `FUTURE_ARCHITECTURE.md`'s
  own "C — Computational uncertainty" upgrade already names the same
  principle for investigation findings.
- **§24, the Verification Engine** — unlike the entries above (existing
  precedent this document generalizes), this one is no longer only
  named in the vision: `financial_system/verification/` is a real,
  running, additive-only instance of it, built independent of Risk/
  Recovery/Controller's own decision code. Four of the section's eleven
  named properties are checked for real, against real verdicts, from
  both the real Heimdall dataset and a bridged `Simulation/` (Truman)
  run: replay correctness (rebuilding the real financial state store
  twice, byte-identical), temporal integrity (auditing Risk's real
  as-of mechanism — 0 boundary violations across the full real and
  bridged corpora, plus one real, separately-diagnosed raw-data
  timestamp finding named, not hidden, in
  `financial_system/verification/README.md`), evidence grounding
  (zero dangling evidence ids across all three domains, both sources),
  and idempotency (byte-identical `AgentVerdict` output on repeat
  calls). See `financial_system/verification/README.md` for the full
  real numbers and the honest list of what the other seven properties
  would still take to build.

The pattern across all of these: every one was built small, in one
place, verified before moving on — never the other way around. That's
the actual throughline between this document and the rest of the
repository, and it's the reason to treat this as vision to revisit
deliberately, phase by phase, rather than a rebuild to start now.

---

<!-- Verbatim vision document follows, as provided. -->

# HEIMDALL

## System Transformation & Long-Term Development Roadmap

### From Financial Control System → Computational Financial Intelligence System

---

# 0. The New Definition of Heimdall

Heimdall should no longer be defined as a payment-risk, recovery, reconciliation, or fraud system.

Those are **domains implemented on top of Heimdall**.

The long-term definition is:

> **Heimdall is a general financial intelligence and control system capable of representing financial worlds, learning their structure from research and resources, simulating their evolution, reasoning over their state, making policy-constrained decisions, acting on the world, and verifying the consequences.**

The fundamental object is therefore not:

```text
payment
```

but:

```text
WORLD
```

A payment is merely one event occurring inside a financial world.

---

# 1. The Fundamental Architectural Shift

The current system is centered around:

```text
Payment
    ↓
Risk
    ↓
Recovery
    ↓
Policy
    ↓
Action
```

This must evolve into:

```text
                    FINANCIAL WORLD
                          │
                    EVENT HISTORY
                          │
                    WORLD STATE
                          │
              ┌───────────┴───────────┐
              │                       │
         WORLD OBSERVATION        KNOWLEDGE
              │                       │
              └───────────┬───────────┘
                          │
                    INTELLIGENCE
                          │
       ┌──────────────────┼──────────────────┐
       │                  │                  │
     DETECT             PREDICT           EXPLAIN
       │                  │                  │
       └──────────────────┼──────────────────┘
                          │
                     INVESTIGATE
                          │
                   CAUSAL REASONING
                          │
                ECONOMIC REASONING
                          │
                  COUNTERFACTUALS
                          │
                       DECIDE
                          │
                       POLICY
                          │
                       ACTION
                          │
                       OUTCOME
                          │
                    VERIFICATION
                          │
                    WORLD UPDATE
                          │
                          └────────────────↺
```

The system therefore becomes a **closed-loop computational representation of finance**.

---

# 2. The Three Systems That Must Become One

The long-term Heimdall architecture has three major computational systems.

```text
                 DISCOVERY.AI
                      │
              understands finance
                      │
                      ▼
              FINANCIAL WORLD MODEL
                      │
               represents finance
                      │
                      ▼
              SIMULATION ENGINE
                      │
              generates worlds
                      │
                      ▼
                 HEIMDALL
                      │
          observes / reasons / acts
                      │
                      ▼
              simulated or real world
                      │
                      └──────────────↺
```

These are not separate products.

They form a single developmental loop.

### Discovery.AI

Discovers:

* entities
* relationships
* events
* mechanisms
* rules
* behaviors
* institutions
* constraints
* models
* research findings
* causal hypotheses
* evaluation methods

### World Engine

Formalizes those discoveries into:

* ontology
* state
* event structures
* relationships
* institutions
* contracts
* ledgers
* policies
* mechanisms

### Simulation Engine

Uses the world specification to generate:

* agents
* institutions
* transactions
* economic behavior
* failures
* shocks
* interventions
* outcomes

### Heimdall Intelligence

Operates over the resulting world:

* observes
* detects
* predicts
* investigates
* reasons
* evaluates
* decides
* acts
* verifies

---

# 3. Systemic Change #1 — Make the Financial World the Primary Abstraction

The current architecture is too payment-centric.

Heimdall must gain a universal world model.

The canonical ontology should eventually contain entities such as:

```text
PERSON
HOUSEHOLD
CUSTOMER
MERCHANT
COMPANY
BANK
ACCOUNT
CARD
PAYMENT_METHOD
DEVICE
COUNTERPARTY
INSTITUTION
REGULATOR
GOVERNMENT
CENTRAL_BANK
FUND
INSURER
```

But entities alone are insufficient.

The world also requires:

```text
EVENTS
STATES
RELATIONSHIPS
CONTRACTS
OBLIGATIONS
BALANCES
POLICIES
OWNERSHIP
IDENTITY
EXPOSURES
```

The world model must answer:

> What exists?

> What happened?

> What is true now?

> What was true at time t?

> What caused what?

> Who is connected to whom?

> What does each entity own or owe?

> What obligations exist?

> What constraints govern the system?

---

# 4. Systemic Change #2 — Make Events Universal

Every meaningful state transition must become an event.

For example:

```text
CustomerCreated
AccountOpened
CardIssued

PaymentInitiated
AuthorizationAttempted
AuthorizationSucceeded
AuthorizationFailed

AuthenticationRequested
AuthenticationCompleted

RetryRequested
RetryCompleted

RefundIssued
ChargebackOpened
ChargebackResolved

LoanCreated
InstallmentDue
InstallmentPaid
LoanDefaulted

SettlementCreated
SettlementAdjusted

FeeApplied
BalanceChanged

RiskDecision
RecoveryDecision
InvestigationCreated

PolicyDecision
ActionRequested
ActionOutcomeObserved
```

The event system becomes the backbone of the entire world.

The principle remains:

> **The current state is a projection of history.**

Therefore:

```text
EVENT HISTORY
      ↓
STATE PROJECTION
      ↓
WORLD STATE(t)
```

This must work across every financial domain.

---

# 5. Systemic Change #3 — Generalize Temporal Reality

Time must become a universal primitive.

Every observation must have an information boundary.

The system must distinguish:

```text
what happened
```

from:

```text
what was knowable at the time
```

The current temporal Risk fix is therefore not a special Risk feature.

It becomes a **core World Observation primitive**.

Eventually:

```text
WorldSnapshot(
    as_of = t,
    observer = X,
    scope = Y
)
```

Everything downstream operates against an explicit snapshot.

This applies to:

* Risk
* Recovery
* AML
* Credit
* Treasury
* Settlement
* Investigation
* Economic reasoning
* Counterfactuals
* Policy
* Replay

No intelligence component should silently see the future.

---

# 6. Systemic Change #4 — Build a Real World Registry

Heimdall needs a canonical registry of everything that exists in its world.

```text
WORLD REGISTRY
│
├── Entity Registry
├── Identity Registry
├── Account Registry
├── Instrument Registry
├── Institution Registry
├── Contract Registry
├── Ownership Registry
├── Relationship Registry
├── Event Registry
├── Obligation Registry
├── Ledger Registry
├── Policy Registry
├── Agent Registry
└── Regulatory Registry
```

This eliminates the idea that every domain owns its own disconnected universe.

There should be one world.

Domains interpret different parts of that world.

---

# 7. Systemic Change #5 — Separate World, Knowledge and Evidence

Heimdall should eventually contain three distinct but connected graph structures.

## World Graph

What exists and what happened.

```text
Customer
 └── owns → Account
              └── initiated → Payment
```

## Knowledge Graph

What is known about financial systems.

```text
Insufficient Funds
 └── typically leads to → delayed retry
```

## Evidence Graph

Why Heimdall believes something.

```text
CLAIM
  ↓
DERIVATION
  ↓
EVIDENCE
  ↓
SOURCE
```

These must not be conflated.

A research statement is not a world fact.

A model inference is not an observed event.

An LLM hypothesis is not ground truth.

---

# 8. Systemic Change #6 — Turn Discovery.AI Into the Research-to-World Engine

Discovery.AI becomes much more than an investigation agent.

Its long-term role is:

> **Discover the structure of financial reality and convert knowledge into formalizable world components.**

Input:

```text
Papers
Datasets
Models
Regulations
Industry Documents
Case Studies
Technical Documentation
Institutional Reports
```

Discovery extracts:

```text
Entities
Events
Relationships
Mechanisms
Rules
Behavior
Equations
Constraints
Failure Modes
Interventions
Evaluation Methods
```

Then:

```text
RESEARCH
   ↓
DISCOVERY
   ↓
FINANCIAL KNOWLEDGE
   ↓
FORMALIZATION
   ↓
WORLD MODEL
```

This creates the connection between the original Discovery.AI project and Heimdall.

---

# 9. Systemic Change #7 — Research Must Become Executable

Research should eventually stop being merely informational.

A research finding can become a formal mechanism.

For example:

```text
Research:
Consumers change spending based on income and liquidity.
```

Discovery.AI extracts:

```text
MECHANISM

P(action | income, liquidity, obligations, preferences)
```

The mechanism becomes a simulation component.

The simulator then produces agents exhibiting that behavior.

The resulting behavior can be evaluated against real observations.

Therefore:

```text
RESEARCH
   ↓
MECHANISM
   ↓
FORMAL MODEL
   ↓
SIMULATOR
   ↓
OBSERVATIONS
   ↓
VALIDATION
```

Research becomes one of the ways the world itself is constructed.

---

# 10. Systemic Change #8 — Build the Agent-Based Financial World

Heimdall should eventually be able to construct worlds populated by agents.

Agents include:

```text
Individuals
Households
Merchants
Companies
Banks
Lenders
Investors
Insurers
Payment Networks
Regulators
Government Institutions
```

Agents operate according to:

```text
STATE
+
OBJECTIVES
+
INCENTIVES
+
CONSTRAINTS
+
POLICIES
+
PROBABILISTIC BEHAVIOR
```

For example:

```text
P(action | state, incentives, constraints)
```

The world should not require an LLM to generate every action.

Most world behavior should be:

```text
deterministic
+
probabilistic
+
rule-based
+
mechanism-based
```

LLMs belong primarily in higher-level reasoning and discovery—not as the physics engine of finance.

---

# 11. Systemic Change #9 — Build Institutions as Computational Systems

The simulator must eventually model institutions, not just transactions.

A bank should have:

```text
CUSTOMER SYSTEM
ACCOUNT SYSTEM
PAYMENT SYSTEM
CREDIT SYSTEM
LEDGER
TREASURY
LIQUIDITY
RISK
FRAUD
AML
COMPLIANCE
SETTLEMENT
REPORTING
POLICY
```

Similarly:

```text
MERCHANT
PAYMENT NETWORK
INSURER
LENDER
EXCHANGE
FUND
REGULATOR
```

should have their own internal state and mechanisms.

Institutions interact through standardized events and obligations.

This creates an actual **computable financial ecosystem**.

---

# 12. Systemic Change #10 — Replace "Synthetic Dataset" With "Simulated World"

The objective is not:

```text
generate fake CSV
```

It is:

```text
construct world
      ↓
run world
      ↓
observe world
      ↓
record complete history
```

The resulting dataset is merely a projection of the world.

This is a fundamental distinction.

Instead of:

```text
row 1
row 2
row 3
```

we get:

```text
WORLD
 │
 ├── Person A
 │    ├── income
 │    ├── account
 │    ├── expenses
 │    └── loan
 │
 ├── Bank A
 │    ├── deposits
 │    ├── loans
 │    ├── reserves
 │    └── liquidity
 │
 └── Merchant B
      ├── sales
      ├── refunds
      └── settlement
```

Transactions emerge from those relationships.

---

# 13. Systemic Change #11 — Use Real Datasets as Calibration, Not Definition

Real datasets remain important.

But their role changes.

They become:

```text
CALIBRATION
VALIDATION
BENCHMARKING
DISTRIBUTION ESTIMATION
REAL-WORLD CONSTRAINTS
```

rather than:

```text
"this dataset defines finance"
```

The architecture becomes:

```text
REAL WORLD
   │
   ├── DATA
   │
   └── RESEARCH
        │
        ▼
   WORLD MODEL
        │
        ▼
    SIMULATION
        │
        ▼
 SYNTHETIC WORLDS
        │
        ▼
 TRAINING / TESTING
        │
        ▼
    HEIMDALL
```

This allows the system to escape the limitations of any single dataset.

---

# 14. Systemic Change #12 — Build a Financial Simulation Laboratory

The simulator becomes an experimental environment.

Heimdall should be able to create:

```text
BASE WORLD
```

and then produce:

```text
WORLD A
WORLD B
WORLD C
...
WORLD N
```

by changing:

```text
interest rates
fraud prevalence
consumer behavior
bank policy
regulatory policy
liquidity
economic conditions
payment failures
credit conditions
market conditions
```

Then measure:

```text
loss
risk
liquidity
stability
fraud
default
customer impact
institutional impact
economic utility
```

This becomes the testing laboratory for financial intelligence.

---

# 15. Systemic Change #13 — Build Counterfactual Worlds

Heimdall should eventually be able to ask:

> What happens if we do X instead of Y?

Formally:

```text
CURRENT WORLD
      │
 ┌────┼─────┐
 │    │     │
 A    B     C
 │    │     │
 ▼    ▼     ▼
WA   WB    WC
 │    │     │
 └────┼─────┘
      ▼
 COMPARE
```

This becomes the basis of:

* policy evaluation
* economic optimization
* risk management
* intervention analysis
* strategy
* stress testing

---

# 16. Systemic Change #14 — Build a General Economic Engine

The existing EV/R0 architecture should evolve into a universal economic reasoning system.

Eventually:

```text
ExpectedUtility(action, world)
=
expected benefit
− expected cost
− expected loss
− expected risk
− opportunity cost
```

Every term must have:

```text
value
source
uncertainty
time horizon
assumptions
```

If the system cannot justify a term:

```text
UNKNOWN
```

It must not fabricate precision.

This becomes the common economic substrate for:

```text
Payments
Recovery
Credit
Fraud
AML
Treasury
Settlement
Insurance
Markets
```

---

# 17. Systemic Change #15 — Generalize Intelligence

The current Risk/Recovery/Controller architecture should become a general intelligence framework.

Every domain intelligence module should follow the same structure:

```text
DOMAIN
 │
 ├── Signals
 ├── Deterministic Rules
 ├── Statistical Models
 ├── Graph Models
 ├── Predictions
 ├── Investigation
 ├── Hypotheses
 ├── Confidence
 ├── Economic Analysis
 ├── Recommended Actions
 └── Evaluation
```

The domain module does not own the world.

It reasons over the world.

---

# 18. Systemic Change #16 — Preserve Deterministic Systems as the Guarantee Layer

AI should not replace deterministic finance.

Instead:

```text
DETERMINISTIC
     +
STATISTICAL
     +
AGENTIC
```

should work together.

Deterministic systems handle:

```text
ledger arithmetic
balances
state transitions
policy constraints
invariants
temporal boundaries
authorization
reconciliation
idempotency
```

Statistical systems handle:

```text
prediction
classification
probability
anomaly detection
forecasting
```

Agentic systems handle:

```text
investigation
planning
hypothesis generation
evidence gathering
complex reasoning
```

This division is fundamental.

---

# 19. Systemic Change #17 — Upgrade Discovery From "Answering" to "Investigating"

Discovery.AI should become an epistemic engine.

The investigation pipeline becomes:

```text
QUESTION
   ↓
QUESTION DECOMPOSITION
   ↓
EVIDENCE PLAN
   ↓
RETRIEVAL
   ↓
FACT EXTRACTION
   ↓
RELATIONSHIP DISCOVERY
   ↓
INFERENCE
   ↓
HYPOTHESIS
   ↓
VALIDATION
   ↓
CONFIDENCE
   ↓
CONCLUSION / UNKNOWN
```

The system must be allowed to say:

```text
UNKNOWN
```

when evidence is insufficient.

That remains one of the most important properties of the architecture.

---

# 20. Systemic Change #18 — Build an Epistemic Layer

Every piece of knowledge must have a status.

```text
OBSERVED
CORRELATED
INFERRED
CAUSAL
HYPOTHETICAL
```

And:

```text
FACT
 ↓
OBSERVATION
 ↓
INFERENCE
 ↓
HYPOTHESIS
 ↓
CAUSAL CLAIM
```

Evidence requirements increase as the system moves upward.

This prevents:

```text
association
   ↓
false certainty
   ↓
bad financial decision
```

---

# 21. Systemic Change #19 — Make Policy a First-Class Computational Object

Policy should not be an afterthought around agents.

A policy must define:

```text
PRECONDITIONS
EVIDENCE REQUIREMENTS
RISK LIMITS
ECONOMIC LIMITS
TEMPORAL CONSTRAINTS
AUTHORIZED ACTIONS
FORBIDDEN ACTIONS
ESCALATION
APPROVAL
```

Therefore:

```text
INTELLIGENCE
     ↓
RECOMMENDATION
     ↓
POLICY
     ↓
AUTHORIZATION
     ↓
ACTION
```

Agents never directly control consequential financial actions.

---

# 22. Systemic Change #20 — Build a General Action System

The existing Action lifecycle becomes the universal control mechanism.

```text
ActionRequested
       ↓
PolicyAuthorization
       ↓
ActionExecutionStarted
       ↓
External/System Action
       ↓
ActionOutcomeObserved
       ↓
World State Change
```

The outcome—not the requested action—changes the world.

This principle must remain universal.

---

# 23. Systemic Change #21 — Add Temporal and Conditional Actions

The action system should eventually support:

```text
DO NOW
DO LATER
WAIT UNTIL
RE-EVALUATE WHEN
ESCALATE IF
CANCEL IF
RETRY IF
```

For example:

```text
Insufficient funds
      ↓
WAIT 24 HOURS
      ↓
RE-EVALUATE WORLD
      ↓
IF liquidity recovered
      ↓
retry
```

This turns Heimdall from a decision engine into a **temporal control system**.

---

# 24. Systemic Change #22 — Build the Verification Engine

Verification must become independent from intelligence.

It should verify:

```text
Was the observation valid?
Was the state correct?
Was future information leaked?
Was the reasoning grounded?
Was the policy satisfied?
Was the economic calculation correct?
Was the action authorized?
Was the action idempotent?
Did the outcome occur?
Was the world updated correctly?
Can the decision be replayed?
```

This becomes a universal audit layer.

---

# 25. Systemic Change #23 — Build Adversarial Worlds

The simulation engine should deliberately create worlds designed to break Heimdall.

Examples:

```text
fraud pattern shifts
identity networks change
bank liquidity shock
mass refunds
settlement failure
payment network outage
merchant collusion
account takeover
credit crisis
regulatory change
unexpected customer behavior
```

Then:

```text
WORLD
 ↓
HEIMDALL
 ↓
DECISION
 ↓
FAILURE?
 ↓
ANALYZE
 ↓
IMPROVE
```

This becomes continuous adversarial development.

---

# 26. Systemic Change #24 — Build a Domain Package Architecture

Every new financial domain should plug into the same substrate.

A domain package contains:

```text
DOMAIN
│
├── Ontology
├── Entities
├── Events
├── State
├── Relationships
├── Mechanisms
├── Signals
├── Models
├── Agents
├── Policies
├── Actions
├── Outcomes
├── Evidence
└── Evaluators
```

Therefore:

```text
PAYMENTS
AML
CREDIT
FRAUD
SETTLEMENT
ACCOUNTING
TREASURY
INSURANCE
MARKETS
```

all become packages over one world.

---

# 27. The Initial Deep Domains

The system should progressively support:

## Payments

```text
authorization
authentication
retry
refund
chargeback
settlement
fees
routing
```

## Fraud

```text
identity
device
behavior
network
account takeover
merchant abuse
transaction fraud
```

## AML

```text
transactions
counterparties
beneficial ownership
networks
structuring
layering
mules
```

## Credit

```text
applications
underwriting
loans
exposure
installments
delinquency
default
collections
recovery
```

## Settlement

```text
clearing
settlement
netting
adjustments
fees
reconciliation
obligations
```

## Accounting

```text
ledger
journal
accounts
assets
liabilities
equity
accruals
adjustments
financial statements
```

## Treasury

```text
cash
liquidity
funding
reserves
exposure
forecasting
counterparties
```

## Insurance

```text
policy
premium
risk
claim
loss
reserve
payout
fraud
```

## Markets

Eventually:

```text
orders
trades
positions
portfolios
market state
derivatives
exposure
settlement
```

---

# 28. The Research Engine Must Continuously Expand These Domains

Research should periodically ask:

```text
What exists in this domain?

What mechanisms are known?

What entities are missing?

What events are missing?

What relationships are missing?

What models exist?

What empirical evidence exists?

What failure modes exist?

What interventions exist?

What evaluation methods exist?
```

This produces a:

```text
CAPABILITY GRAPH
```

showing:

```text
SUPPORTED
PARTIAL
UNKNOWN
MISSING
UNVERIFIED
```

That graph drives future engineering.

---

# 29. The Simulation Engine Must Become a World Generator

The simulation engine eventually needs:

```text
WORLD CONFIGURATION
        ↓
ENTITY GENERATION
        ↓
INSTITUTION GENERATION
        ↓
RELATIONSHIP GENERATION
        ↓
INITIAL STATE
        ↓
AGENT BEHAVIOR
        ↓
EVENT GENERATION
        ↓
STATE TRANSITION
        ↓
EVENT LOG
```

It should support:

```text
random worlds
parameterized worlds
research-derived worlds
historically calibrated worlds
stress worlds
adversarial worlds
counterfactual worlds
```

---

# 30. The Simulator Must Be Reproducible

Every simulated world should have:

```text
world_id
seed
configuration
model_versions
mechanism_versions
policy_versions
research_sources
initial_state
event_history
```

Then:

```text
same seed
+
same configuration
+
same versions
=
same world
```

This is essential for scientific evaluation.

---

# 31. Sampling Becomes a Core Capability

Once the simulator exists, Heimdall can sample worlds.

```text
World Distribution
        │
        ▼
W₁ W₂ W₃ W₄ ... Wₙ
        │
        ▼
OBSERVATIONS
        │
        ├── training
        ├── evaluation
        ├── stress testing
        ├── policy testing
        └── model comparison
```

The unit of evaluation can therefore become:

> **a world**

rather than:

> a row.

That is a major conceptual improvement.

---

# 32. Training Must Eventually Become Environment-Based

Models and agents should be trained/evaluated against distributions of worlds.

For example:

```text
TRAIN WORLDS
   ↓
agent/model
   ↓
UNSEEN WORLDS
   ↓
evaluation
```

This tests whether the system learned mechanisms rather than memorized a dataset.

The simulator becomes an environment.

Heimdall becomes the intelligence operating within that environment.

---

# 33. But Simulation Must Never Become Fake Truth

This is a hard architectural rule.

Every simulation mechanism must carry:

```text
SOURCE
EVIDENCE
ASSUMPTIONS
CALIBRATION
UNCERTAINTY
VALIDITY RANGE
FAILURE MODES
```

The system must distinguish:

```text
REAL OBSERVATION
RESEARCH-SUPPORTED MECHANISM
CALIBRATED SIMULATION
PLAUSIBLE ASSUMPTION
HYPOTHETICAL SCENARIO
```

Synthetic evidence cannot silently become empirical evidence.

---

# 34. Systemic Change #25 — Create a Research Provenance System

Every research-derived component should remember:

```text
source
source type
author
publication
date
domain
claim
extracted mechanism
formalization
assumptions
confidence
validation status
```

Therefore the simulator can answer:

> Why does this mechanism exist?

and Heimdall can answer:

> Why did this mechanism influence this decision?

This creates a continuous provenance chain:

```text
RESEARCH
 ↓
KNOWLEDGE
 ↓
WORLD MODEL
 ↓
SIMULATION
 ↓
OBSERVATION
 ↓
INTELLIGENCE
 ↓
DECISION
 ↓
ACTION
```

---

# 35. Systemic Change #26 — Build a Unified Evaluation Framework

Every capability must eventually have:

```text
UNIT TESTS
INVARIANTS
SCENARIO TESTS
TEMPORAL TESTS
ADVERSARIAL TESTS
COUNTERFACTUAL TESTS
CALIBRATION TESTS
REPLAY TESTS
REAL-DATA VALIDATION
SIMULATION VALIDATION
```

And the evaluation system should measure more than accuracy.

Examples:

```text
precision
recall
false-positive rate
calibration
economic loss
expected utility
robustness
stability
policy violations
temporal leakage
grounding
replay correctness
```

---

# 36. Systemic Change #27 — Make the Architecture Self-Expanding

The ultimate development loop becomes:

```text
RESEARCH
    ↓
DISCOVER
    ↓
IDENTIFY MISSING CAPABILITY
    ↓
FORMALIZE
    ↓
EXTEND WORLD MODEL
    ↓
EXTEND SIMULATOR
    ↓
GENERATE WORLDS
    ↓
BUILD INTELLIGENCE
    ↓
ADVERSARIAL TEST
    ↓
VERIFY
    ↓
INTEGRATE
    ↓
NEW CAPABILITY
    ↓
RESEARCH AGAIN
```

This is the long-term engine for Heimdall's growth.

The system doesn't need to know every financial domain today.

It needs an architecture capable of **continuously learning what it is missing and adding it without breaking the substrate**.

---

# 37. The Final Heimdall Architecture

Eventually the system should look approximately like:

```text
                         ┌───────────────────────┐
                         │      RESEARCH         │
                         │ Papers / Data / Laws  │
                         │ Models / Institutions │
                         └───────────┬───────────┘
                                     │
                                     ▼
                         ┌───────────────────────┐
                         │     DISCOVERY.AI      │
                         │                       │
                         │ ontology discovery    │
                         │ mechanism discovery   │
                         │ evidence               │
                         │ reasoning              │
                         └───────────┬───────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │      FINANCIAL KNOWLEDGE       │
                    │ rules / mechanisms / models    │
                    └────────────────┬───────────────┘
                                     │
                                     ▼
        ┌─────────────────────────────────────────────────────┐
        │                 FINANCIAL WORLD                     │
        │                                                     │
        │ entities / relationships / contracts / obligations │
        │ accounts / institutions / balances / ledgers       │
        │                                                     │
        │ events ───────────────► temporal state              │
        └────────────────────────┬────────────────────────────┘
                                 │
                     ┌───────────▼────────────┐
                     │   SIMULATION ENGINE    │
                     │                        │
                     │ agents                 │
                     │ institutions           │
                     │ behavior               │
                     │ economics              │
                     │ shocks                 │
                     │ counterfactuals        │
                     └───────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │      HEIMDALL           │
                    │                         │
                    │ OBSERVE                 │
                    │ DETECT                  │
                    │ PREDICT                 │
                    │ INVESTIGATE             │
                    │ EXPLAIN                 │
                    │ REASON                  │
                    │ ECONOMICALLY             │
                    │ COUNTERFACTUALLY        │
                    │ DECIDE                  │
                    └───────────┬─────────────┘
                                │
                                ▼
                         ┌──────────────┐
                         │    POLICY    │
                         │ authorization│
                         │ constraints  │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │    ACTION    │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │   OUTCOME    │
                         └──────┬───────┘
                                │
                                ▼
                         WORLD STATE UPDATE
                                │
                                └──────────────↺
```

Surrounding everything:

```text
TIME
IDENTITY
PROVENANCE
EVIDENCE
UNCERTAINTY
CAUSALITY
POLICY
SECURITY
VERIFICATION
REPLAY
```

These are not features.

They are **system invariants**.

---

# 38. The Development Order

The programs should not be treated as 27 independent implementation phases.

They form a dependency structure.

## Foundation

```text
1. Universal World Model
2. Universal Event Model
3. Temporal Observation
4. World Registry
5. Provenance
6. Graph
7. State Projection
```

↓

## Research / Knowledge

```text
8. Discovery.AI Research Pipeline
9. Knowledge Representation
10. Evidence Graph
11. Research Provenance
12. Mechanism Formalization
```

↓

## Simulation

```text
13. Agent Framework
14. Institution Framework
15. Behavioral Mechanisms
16. Economic Mechanisms
17. World Generator
18. Scenario Engine
19. Counterfactual Engine
```

↓

## Intelligence

```text
20. Deterministic Intelligence
21. Statistical Intelligence
22. Graph Intelligence
23. Investigation
24. Causal Reasoning
25. Economic Reasoning
26. Uncertainty
```

↓

## Control

```text
27. Policy Engine
28. Authorization
29. Action Engine
30. Temporal Actions
31. Outcome Processing
```

↓

## Verification

```text
32. Replay
33. Invariant Verification
34. Calibration
35. Adversarial Worlds
36. Cross-world Evaluation
```

↓

## Domain Expansion

```text
37. Payments
38. Fraud
39. AML
40. Credit
41. Settlement
42. Accounting
43. Treasury
44. Insurance
45. Markets
...
```

↓

## Self Expansion

```text
46. Capability Discovery
47. Research Gap Detection
48. Automatic World Extension
49. New Scenario Generation
50. Continuous Evaluation
```

---

# 39. What Happens to the Current Heimdall?

We do NOT throw it away.

The existing system becomes **Version 0 of the larger architecture**.

Current:

```text
Event sourcing
State projection
Graph
Temporal Risk
Recovery
EV
Controller
Investigation
Policy
Action
Outcome
Replay
Verification
```

becomes the first working vertical slice of:

```text
WORLD
 ↓
OBSERVE
 ↓
INTELLIGENCE
 ↓
ECONOMICS
 ↓
POLICY
 ↓
ACTION
 ↓
OUTCOME
 ↓
VERIFY
```

The next architectural goal is to **generalize the machinery**, not replace proven components unnecessarily.

---

# 40. The First Proof of the New Architecture

The system should eventually prove that two radically different financial domains can operate on the same substrate.

For example:

```text
PAYMENTS
+
AML
```

or:

```text
PAYMENTS
+
CREDIT
```

using the same:

```text
world model
event system
temporal system
graph
provenance
research layer
simulation engine
intelligence framework
economic engine
policy engine
action engine
verification engine
```

If this works, then Heimdall has demonstrated that it is genuinely becoming a **financial operating substrate**, rather than a collection of payment-specific systems.

---

# 41. The Ultimate Loop

The deepest version of Heimdall is:

```text
                 REAL FINANCIAL WORLD
                         │
                         ▼
                     RESEARCH
                         │
                         ▼
                    DISCOVERY
                         │
                         ▼
                  WORLD KNOWLEDGE
                         │
                         ▼
                  WORLD FORMALIZATION
                         │
                         ▼
                    SIMULATION
                         │
                         ▼
                  MANY FINANCIAL WORLDS
                         │
                         ▼
                    OBSERVATIONS
                         │
                         ▼
                    INTELLIGENCE
                         │
                         ▼
                 ECONOMIC REASONING
                         │
                         ▼
                    COUNTERFACTUAL
                         │
                         ▼
                      POLICY
                         │
                         ▼
                      ACTION
                         │
                         ▼
                      OUTCOME
                         │
                         ▼
                    VERIFICATION
                         │
                         ▼
                  NEW KNOWLEDGE
                         │
                         └──────────────────↺
```

The system therefore becomes capable of doing something fundamentally different:

> **It does not merely consume financial data. It constructs a computational representation of financial reality, studies that reality, experiments on it, reasons over it, controls it, and continuously expands its understanding of it.**

---

# 42. The North Star

The final objective is not:

```text
better fraud detection
```

or:

```text
better payment recovery
```

or:

```text
more financial agents
```

Those are individual capabilities.

The north star is:

> **Build a computational financial world in which financial entities, institutions, behaviors, mechanisms, transactions, risks, obligations, policies and consequences can be represented, simulated, reasoned about, acted upon and verified.**

Discovery.AI discovers the structure.

The World Engine represents the structure.

The Simulation Engine makes the structure evolve.

The Intelligence Engine understands the evolving world.

The Economic Engine evaluates consequences.

The Policy Engine governs decisions.

The Action Engine changes the world.

The Verification Engine determines whether the entire chain can be trusted.

And the Research Engine continuously discovers what the system still does not understand.

That is the systemic transformation of Heimdall.

**Heimdall stops being a financial application and becomes the substrate on which financial intelligence systems can be built.**
