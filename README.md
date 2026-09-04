# Project Heimdall

**Financial Intelligence & Action System — AI Revenue Recovery.** Named
for the Norse guardian who sees across all nine realms at once: this
system watches risk, reconciliation, and recovery over one shared
financial world, rather than three disconnected views. Built on
Discovery.AI, a recursive investigation engine over a knowledge graph,
repurposed as the reasoning substrate underneath a deterministic
financial decision-and-action system.

> Failed payments don't need another retry button. They need a financial
> system that can understand why revenue is at risk, decide what action
> is justified, execute it safely, and verify what actually happened.

## The problem

The naive fix for payment failures is "retry everything." That trades one
loss for another: duplicate charges, wasted gateway calls, and blind
retries on payments that were never going to succeed. The real question
isn't *"should we retry failed payments,"* it's:

- Which failures are worth retrying, and which aren't — reliably, not by
  guessing?
- When do you stop retrying a payment that keeps failing?
- Can you prove, after the fact, exactly why the system did what it did —
  what world it reasoned over, under which policy, authorizing which
  action?

That last question is usually where financial-agent demos quietly stop
being honest. This one doesn't.

## What it does — one concrete run

A payment fails with `technical_failure`. Recovery classifies the
*category* as recoverable (a real decline-code taxonomy, not a guess) and
proposes a retry, scored at the category's own historical success rate —
never a promise about this one payment. Policy checks the proposal
against deterministic rules and authorizes it. The action executes
(simulated gateway, by design — see Limitations). The gateway reports
success. That becomes a durable event, which changes the payment's
recorded state. The system is asked about the *same payment* again, from
scratch, with no memory carried over in code — and independently
concludes there's nothing left to recover.

Nobody told the second reasoning pass that the first attempt succeeded.
It found out the same way anything else in this system finds out: from
the event log.

## The loop

```
Payment Failed
      |
Recovery Signals            (deterministic: a real decline-code taxonomy)
      |
Investigation, when the failure reason is genuinely unrecognized
      |
Decision                     (decision_score = category base rate, never a per-instance guess)
      |
Policy                       (deterministic rules; an LLM's confidence cannot authorize money)
      |
Action                       (idempotent, durable, crash-safe)
      |
Observed Outcome             (a new, timestamped event)
      |
Financial State              (a projection of the event log, not a second source of truth)
      |
Fresh Recovery                (asked again, independently, on the changed world)
```

## Why this isn't just an LLM wrapper

```
Deterministic financial truth
          +
Evidence-driven investigation (only when deterministic evidence runs out)
          +
Policy-controlled action (no LLM output ever authorizes money)
          +
Verification (the action's real outcome, not the model's opinion of it)
```

Every domain agent (Risk, Controller, Recovery) computes its own
`decision` and `decision_score` deterministically — a lookup, a
reconciliation arithmetic check, a category base rate. Discovery.AI is
invoked only when that deterministic evidence is genuinely insufficient,
and its output — a narrative and a confidence score — is carried for
**audit only**. `PolicyDecision` has no field for it at all, structurally,
not by convention: no future code path can accidentally read it as
authorization. A real adversarial test proves this boundary holds: a
fabricated `investigation_confidence` of 0.99 cannot authorize an action
whose deterministic `decision_score` is only 0.20.

## Proven results

| Metric | What it actually means | Proof |
|---|---|---|
| 100% category-recoverability accuracy | Every failure category correctly classified recoverable/not, against ground truth | `recovery/runner.py` |
| 100% recovery rate (87/87) | Every recoverable-category case was correctly *attempted* — a consequence of the classification rule, **not 87 successful recoveries** and not a prediction claim | `recovery/runner.py` |
| 39.6% false-retry rate | Retries that were attempted but genuinely failed — matches the categories' own weighted historical base rate (39.3% expected) almost exactly. 0% would require an oracle; we didn't fake one. | `recovery/runner.py` |
| `MAX_ATTEMPTS` stopping rule | A payment is never retried indefinitely — escalates to a human after 2 genuine attempts, never repeats the same failed action blindly | `action/runner.py` |
| 555/610 settlement match rate (91.0%) | Automated reconciliation, zero LLM calls -- verified this session to hold with or without Discovery.AI enabled, since Controller's `decision` structurally never changes based on investigation output (`controller.py`'s own boundary) | `reconciliation/runner.py` |
| 47/50 honest-exception rate (94.0%) | Of the genuinely unexplainable cases, correctly left unresolved rather than guessed at | `reconciliation/runner.py` |
| 100% precision / 96.3% recall / 0% FPR | Fraud-ring detection, including 16 deliberately-planted benign traps that must NOT be flagged | `risk/` runner |
| 77/610 settlements | A genuine accounting-consistency gap (`gross - fee - tax != net`) found this project, that operational reconciliation alone never catches — 62 of them look operationally "clean" | `reconciliation/accounting_consistency_test.py` |
| Durable action + outcome history | Idempotent actions, crash-safe recovery, exactly-once financial-state mutation | `action/stage3_runner.py`, `stage4_runner.py` |
| Historical decision provenance | A stored decision, replayed against the exact world it was made against, reproduces itself exactly | `decisions/adversarial_test.py` |

## Live demo

You will watch, live, not from a script:

1. A real failed payment, reasoned about by Recovery.
2. A policy check that authorizes (or blocks) the proposed action.
3. The action executing against a simulated gateway.
4. The gateway's outcome becoming a durable event.
5. The payment's state changing as a *result* of that event, not a
   hand-written patch.
6. Recovery asked again, independently, on the new world — reaching a
   different, correct conclusion with no special-case code anywhere for
   "this was a successful retry."

That last step is the actual claim this project makes: the system has
temporal memory, and its reasoning is a function of what's currently
true, not what it happened to conclude a moment ago.

## Architecture

```
                 FINANCIAL WORLD (event-sourced, temporally honest)
                       |
          +------------+------------+
          v            v            v
        RISK       CONTROLLER     RECOVERY   <- this submission's focus
          |            |            |
          +------------+------------+
                       v
                  DISCOVERY.AI  (investigates; never decides)
                       |
                       v
                    POLICY  ->  DECISION RECORD  ->  ACTION  ->  OUTCOME
                                                                    |
                                                                    v
                                                          (back into WORLD)
```

Risk, Controller, and Recovery reason over the *same* graph and can
disagree productively: a real cross-domain conflict check caught 25 cases
(across all 1000 payments) where two independently-correct verdicts —
e.g. Risk flags a device, Recovery proposes a retry on it — needed to be
escalated together rather than acted on separately.

## Failure recovery — what actually broke, and how we found it

Real incidents, each caught by a test built to attack a specific claim,
not discovered by accident:

1. **A replay test caught a decision-provenance bug with the timing
   backwards.** A decision's recorded "world state at the time" was
   stamped *after* the action it authorized had already executed. Since
   the action's own outcome landed before that timestamp, replaying the
   decision against its own recorded world silently saw its own future
   outcome — a stored `RETRY` replayed back as `DO_NOT_RETRY`. Fixed by
   moving the timestamp to before the reasoning runs, not after.
2. **A re-entry test exposed a real gap in how the system understood
   "attempt."** After a successful retry, asking Recovery again produced
   a confusing, technically-honest-but-useless answer:
   `"unrecognized failure_reason=None"`. The root cause: Recovery checked
   *why* a payment failed but never checked *whether* it was still
   failed. Fixed with a general status check — verified to give the
   identical answer whether the payment resolved on the first attempt,
   the second, or was never retried at all.
3. **We corrected our own accounting finding.** An early pass claimed 19
   of 610 settlements had a payment-sum inconsistency. Building the real
   check revealed the naive sum wasn't deduplicating a repeated
   settlement-payment link — those 19 were entirely the already-known
   `duplicate_record` anomaly, not a second, independent gap. Corrected
   in the same document that made the original claim, not silently
   dropped.

We caught our own architecture being wrong three times during
development, on purpose, by building adversarial tests specifically to
attack it — not by hoping it was right.

## Limitations — stated up front, not discovered under questioning

- **Simulated gateway, not a live payment API.** `action/simulator.py`'s
  own documented boundary. This is the harness the architecture is built
  to plug a real gateway into, not a claim of production readiness.
- **`decision_score` is a category base rate, never a per-instance
  prediction.** A deliberate design choice, stated as one — a 0%
  false-retry rate would require an oracle.
- **Reasoning and decisions are not fully event-sourced.** Only what
  happened in the world and what actions executed are reconstructable at
  an arbitrary point in time; "what did the system *decide* last
  Tuesday" is answerable only for decisions that led to a real action
  (durably recorded), not for every intermediate finding — a deliberate
  boundary, reasoned through explicitly, not an oversight.
- **Historical replay is conditional, not absolute.** It's proven correct
  assuming entity resolution (which payment belongs to which settlement,
  etc.) hasn't changed since — a named, honest boundary on the
  reproducibility claim, not a silent gap.
- **No general ledger.** A researched, deliberate decision: two targeted
  accounting-consistency checks exposed a real gap without building a
  second, unproven financial subsystem in the time available.

## Technical details

- **Temporal event history**: append-only, closed event taxonomy enforced
  at the write boundary, `recorded_at >= occurred_at` enforced (an event
  cannot be learned about before it happened), timezone-normalized.
- **Projection**: current financial state is a projection of the event
  log; historical state at any cutoff (`as_of`) is the *same* projection
  logic, parameterized by time — not a second database.
- **Idempotency**: the same action request twice produces exactly one
  execution; the same key with different parameters is rejected; a
  simulated mid-execution crash never silently re-executes.
- **Decision provenance**: every consequential decision (one that
  authorized a real action) is durably recorded with the world snapshot,
  logic version, and policy version it was made against, linked to the
  action it authorized.
- **Insert-only discipline**: no financial fact, event, action, or
  decision is ever edited in place — only superseded by a new fact, the
  same principle a real ledger uses, applied without building one.

## Reproduction

```bash
# Phase 0 -- generate the synthetic financial universe (fixed seed)
python -m financial_system.data_generator.generate_dataset

# Core pipeline
python -m financial_system.financial_state.builder        # Phase 1 -- ingestion
python -m financial_system.entity_resolution.runner        # Phase 2 -- entity resolution
python -m financial_system.financial_graph.builder          # Phase 3 -- graph
python -m financial_system.reconciliation.runner         # Phase 5 -- Controller
python -m financial_system.risk.runner                   # Phase 6 -- Risk
python -m financial_system.recovery.runner                # Phase 7 -- Recovery
python -m financial_system.policy.runner                  # Phase 9 -- Policy
python -m financial_system.action.runner                  # Phase 10 -- Action + Verification

# Temporal architecture + decision provenance + accounting checks
python -m financial_system.events.runner                          # event-sourcing replay, Gate 1/2
python -m financial_system.events.asof_runner                     # historical reconstruction
python -m financial_system.events.attempt_runner                  # attempt identity
python -m financial_system.events.adversarial_test                # 8 write-boundary gates
python -m financial_system.events.temporal_adversarial_runner      # cross-boundary attack scenarios
python -m financial_system.decisions.adversarial_test              # decision provenance, 4 gates
python -m financial_system.decisions.provenance_adversarial_review # 7 more gates
python -m financial_system.reconciliation.accounting_consistency_test  # 8 gates, real + synthetic
```

Every script above runs against real ground truth in `data/ground_truth/`
and prints the actual numbers on every run — nothing in this repository
is a cached or hand-edited result.

## What's next

`docs/FUTURE_ARCHITECTURE.md` — the next architectural evolution (a shared
investigation substrate and compound cross-domain reasoning across Risk,
Controller, and Recovery), deliberately not implemented for this
submission, written before being asked rather than after.

`docs/FINANCIAL_INTELLIGENCE_RESEARCH_AND_GAP_REPORT.md` — a bounded audit of
this system against real external benchmarks and production payment
platforms (Razorpay, Adyen, Elliptic, FinQA, Finance Agent Benchmark):
what Heimdall already gets right (several hard-won engineering decisions
turn out to match documented production requirements exactly), and what's
honestly still untested (temporal-drift and class-imbalance robustness
for Risk, cost-sensitive decisioning for Recovery). No implementation
follows from it automatically.

## Beyond the submission: Project Truman and a live bridge

Everything above this section is the frozen, submitted system — unchanged
since submission, its numbers reproducible by running the scripts above,
verbatim. Everything below was built afterward as an explicit research
extension and never touches the frozen code above: every task that built
it was required to prove `git diff --stat` on `financial_system/risk/`,
`recovery/`, `reconciliation/`, `financial_state/`, `financial_graph/`,
`discovery_adapter/`, and `data/` was empty before being trusted, and
Risk's 100.0%/96.3%/0.0% and Recovery's 87/87 (39.6%) baselines were
re-verified, unchanged, after every single addition below — no exceptions.

**`docs/NORTH_STAR.md`** records the long-term vision (Heimdall as a
general financial-world substrate, not a payment-specific system) and,
critically, tracks which parts of that vision are still just diagrams
versus which are now real, working code — updated honestly as each piece
below landed, not written once and left stale.

**Project Truman** (`Simulation/`) is a from-scratch, self-contained,
deterministic, agent-based financial world simulator — built to answer
one specific problem: Heimdall's own synthetic-data generator produces
failures from a per-category coin flip (`retry_would_succeed =
random.random() < spec["retry_success_p"]`), with no connection to any
customer's actual state. Truman's agents have real balances, incomes, and
histories; failures emerge causally from that state. The headline
result — bucketing purchase attempts by balance/income ratio produces a
clean, monotonic 96%→0% failure-rate curve, reproduced across three
seeds — is real evidence the approach works, not asserted. Full account,
including the honest gaps (a measured spend/income-ratio mismatch against
real BLS data, fraud/credit/loans designed but not built), in
`Simulation/README.md` and `Simulation/docs/`.

**The bridge** (`financial_system/bridges/`) connects the two, in stages:

- A one-way, batch bridge runs a finished Truman world through Heimdall's
  real, unmodified Recovery, Risk, and Controller code — all three domains,
  real decisions on real (simulated) data, zero fabricated matches (e.g.
  Risk finds zero fraud rings, honestly, because Truman doesn't simulate
  fraud).
- A **live** loop (`live_recovery_loop.py`) goes further: Heimdall's real
  Recovery logic makes decisions *during* a running Truman world, and a
  RETRY decision causes Truman to actually attempt a real retry against
  the person's real, current balance — proven deterministic (two
  independent runs, byte-identical, down to which retries were attempted
  and their outcomes) and proven non-magical (a retry against an
  insufficient balance honestly fails again).
- A **drift detector** checks Heimdall's live decisions against Truman's
  own *known* mechanisms (not assumptions — the real balance/income curve,
  the exact device-sharing rate) — the one advantage a built simulator has
  over a real dataset: the true generative process is known, so deviation
  from it is diagnosable. It already found one real, statistically
  significant case (p=2.6×10⁻⁶): Recovery's stated 0.45 confidence for
  `insufficient_funds` didn't match Truman's realized 0% retry-success
  rate — correctly traced to the live loop's fixed 1-day retry window
  colliding with Truman's monthly-payday-only income model, not a flaw in
  Heimdall's own logic.
- A **verification engine**, a **domain registry** (a structured catalog
  of which Heimdall domains are bridged and exactly what would be needed
  to bridge fraud/credit/loans), and a **provenance catalog** (every
  constant's research-grounded/modeling-assumption/placeholder status,
  indexed and cross-checked against the real code) round out the
  infrastructure — each is read-only or additive-only with respect to
  Heimdall's decision logic.

**Maturity level, stated honestly, the same standard as the Limitations
section above:**

- **Solid**: the causal mechanism itself, double-entry ledger correctness,
  determinism (tested at every layer, including the live loop), the
  zero-impact boundary against Heimdall's frozen code (proven, not
  assumed, on every single addition).
- **Real but small-scale**: the live loop has only been run and verified
  against small populations (20–50 people) — not stress-tested at the
  scale the batch bridge runs at (hundreds of people, thousands of
  transactions).
- **Genuinely uncalibrated**: most of Truman's specific constants are
  labeled, honest modeling assumptions, not numbers verified against real
  data — `Simulation/docs/Research.md` documents exactly which ones are
  cited and which aren't, including numbers that looked tempting and were
  deliberately rejected for failing verification.
- **Not built at all**: fraud, credit scoring, and loan mechanics exist
  only as cited design proposals (`Research.md` Part C); Controller has no
  live loop yet (Risk's live loop is the next one in progress); the
  registry/catalog tools are structured indexes maintained by explicit
  human/agent decisions, not machine learning or autonomous discovery —
  stated plainly in their own docs, not implied by the word "registry."

In short: a real, verified proof that an agent-based simulation with
causal structure can be built and safely wired into a live decision
system without touching that system's own frozen logic — not a claim that
the frozen system's capabilities have grown.

## Track

Submitted under **AI Revenue Recovery**. **AI Finance Controller** and
**AI Risk Manager** are demonstrated as supporting capabilities on the
same substrate, not separate submissions — the point of this
architecture is that Recovery doesn't reason in isolation.
