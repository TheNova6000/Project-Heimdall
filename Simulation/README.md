# Project Truman

A deterministic, agent-based financial world simulator — built as an answer to a
specific, concrete problem: synthetic financial datasets that *look* real but
have no causal structure underneath them.

> Named after *The Truman Show*: a world whose inhabitants act, transact, and
> fail for real reasons, inside a system someone else can observe from
> outside without the inhabitants ever seeing the seams. Every agent here
> spends, saves, and fails to pay for reasons traceable to its own state —
> nothing is a coin flip dressed up as a transaction.

This directory is self-contained. It has zero code dependency on anything
else in this repository (verified: no `import` of `financial_system` code
anywhere in `world/`, `run_simulation.py`, `stats/`, or `validation/` — only
a few explanatory comments mention it by name) — it can be copied out into
its own repository as-is and will run unmodified. It also currently lives
here, connected to Project Heimdall (`financial_system/`) through a one-way,
read-only bridge that lives *outside* this directory (`financial_system/bridges/`),
so nothing in this folder needs to change either way.

## Why this exists

Project Heimdall's real financial-data generator produces failures like this:

```python
retry_would_succeed = random.random() < spec["retry_success_p"]
```

A payment fails because a per-category coin landed wrong — not because the
customer who made it had any particular balance, income, or history. That's
fine for exercising downstream code paths, but it means nothing about *why*
a payment failed is ever really true. Project Truman exists to prove a
different approach is possible: build a small world where agents have real,
evolving state, let failures emerge from that state, and see whether the
result is actually richer — honestly, including if it turns out not to be.

It wasn't obvious this would work. It did:

**The headline finding** (500 persons, 120 days, seed 42): bucketing every
purchase attempt by `balance_before / income_monthly` at the moment of the
attempt produces a clean, monotonic relationship between an agent's own
financial state and whether its next payment fails —

| balance/income ratio | attempts | failure rate |
|---|---|---|
| < 0.02 | 80 | 96.25% |
| 0.02–0.05 | 104 | 70.19% |
| 0.05–0.10 | 133 | 45.86% |
| 0.10–0.25 | 517 | 3.68% |
| ≥ 0.25 | 21,227 | 0.00% |

Reproduced across three separate seeds, same shape every time. This is real
evidence for the thesis: failure risk here is an inspectable function of an
individual agent's own state, not a flat per-category draw — exactly the
structure the real generator's coin flip lacks by construction. See
`docs/Memory.md` for the full derivation, the honest caveats that come with
it (there's a real, reported gap too — naive income-group bucketing shows
almost no signal, because purchase size scales with the buyer's own income),
and the robustness check across seeds.

## What's actually built (not aspirational — every claim below is tested)

```
Person, Bank, Merchant          agents with real probabilistic decision logic
Household, Organization,        structural groupings over agents (own real
 Community, Device                ledger-backed accounts where relevant —
                                   NOT independent decision-makers)
Double-entry ledger              every money movement is a balanced debit/
                                   credit pair; global invariant tested
Merchant settlement              T+1 sweep from pending to spendable balance
Multi-account (checking/savings) a documented fraction of salary auto-swept
Real device-sharing              household members may share one device;
                                   deliberately NO fraud mechanism (see below)
validation/                      samples a run and checks it two ways: against
                                   its own stated rules, and against real cited
                                   research numbers — honestly reports GAPs,
                                   doesn't hide them
```

53 tests, all passing (`python -m pytest tests/ -v`). Determinism is a hard
rule, not a claim: same seed → byte-identical output, checked at both the
in-memory and CSV level, on every phase, every time, including via
independent re-runs outside the test suite (`diff -rq` on two full runs).

**Explicitly not built, on purpose**: fraud, credit scoring, and loan/interest
mechanics. `docs/Research.md` Part C designs all three at a mechanism level,
grounded in real cited statistics (Kansas City Fed fraud-rate data, FRBNY
delinquency-transition rates, Fed loan-pricing research) — but none are
implemented. Building a fraud mechanism casually, just to make a downstream
system's fraud-detection logic have something to find, is exactly the kind
of fabricated-signal shortcut this project exists to avoid. See
`docs/Phases.md` for the full phase-by-phase boundary of what's done vs.
deliberately deferred.

## Quick start

```bash
cd Simulation
python run_simulation.py --seed 42 --population 500 --days 120 --outdir output/run_a
python stats/report.py --outdir output/run_a --save output/run_a/report.md
python validation/sample.py --outdir output/run_a --save output/run_a/validation_report.md
python -m pytest tests/ -v
```

A small real example run is committed at `output/sample/` (seed=1, 25
persons, 14 days) with its own `report.md`, so you can see real output
without running anything first.

## Documentation map

Read in this order if you're picking this project up for the first time:

1. **`docs/PRD.md`** — what this is, why it exists, non-goals, success criteria.
2. **`docs/Architecture.md`** — the data model, the simulation loop, the guiding
   principle (deterministic + probabilistic agents, never an LLM in the loop).
3. **`docs/Rules.md`** — the hard boundaries every phase was held to (provenance
   labeling on every constant, no external downloads without approval, no
   negative balances, determinism, don't scope-creep past the current phase).
4. **`docs/Phases.md`** — what's done, what's explicitly deferred, and why —
   the single source of truth for "is X built yet."
5. **`docs/Design.md`** — output format, naming conventions, code style.
6. **`docs/Research.md`** — real, cited research (Fed, FRBNY, BLS, FRED,
   Stripe) grounding this project's constants, including an honest account of
   which tempting-looking numbers were found and *rejected* because they
   didn't hold up to verification. Part C is the fraud/credit/loan design
   proposal mentioned above.
7. **`docs/Memory.md`** — the living build log. Every design decision, every
   constant's exact provenance, every test's purpose, every honest caveat,
   in the order it actually happened. This is the most detailed document
   here — if a design question isn't answered above, it's answered here.

## Connection to Project Heimdall

This directory doesn't import or depend on `financial_system/` in any way.
The connection runs the other direction: `financial_system/bridges/`
(outside this folder) reads a completed run's output here and transforms it
into Heimdall's real input schema, then calls Heimdall's actual, unmodified
decision code on it — currently bridged for two of Heimdall's three domains
(Recovery, Risk), with real results (not fabricated) documented in
`financial_system/bridges/README.md`. That bridge can be deleted without
this project losing anything, and this project can be extracted into its own
repository without the bridge losing its ability to explain what it once did
(this README and `docs/` stay meaningful on their own).

## Publishing this as its own repository

Nothing here needs to change to do this — copy this directory's contents
into a new repo root and it's a complete, working project:

```bash
# from outside this repo
cp -r Simulation/ project-truman/
cd project-truman/
git init
git add .
git commit -m "Initial commit: Project Truman"
```

The one thing worth updating post-copy: this README's "Connection to Project
Heimdall" section describes a relationship to a sibling project that won't
exist in the new repo's history — trim it or keep it as context, your call.
Everything else (`docs/`, `world/`, `tests/`, `validation/`, `output/sample/`)
is already self-contained and accurate as-is.
