# PRD — Financial World Simulation

## What this is

A standalone, agent-based simulation of a small financial world —
people, banks, merchants — that generates transaction histories through
probabilistic agent behavior rather than hardcoded anomaly injection
(the approach `financial_system/data_generator/` uses) or an LLM.

This is a separate project living alongside Heimdall (`financial_system/`)
in the same repo. It does not modify, depend on, or get depended on by
`financial_system/` in Phase 1. Whether/how the two connect is a later,
explicit decision (Phase 6+), not an assumption baked in now.

## Why

Heimdall's real corpus turned out to have a specific, honestly-discovered
limitation: several capabilities (attempt sequences, recovery timing,
customer financial context) couldn't be built because the *generator*
never encoded the causal structure those capabilities need — not because
the reasoning engine was weak. `retry_would_succeed` is a category-level
coin flip with zero connection to customer, amount, timing, or history,
confirmed by reading the generator's own source.

An agent-based world where transactions emerge from agents acting under
constraints (income, balance, obligations, risk preference) rather than
being drawn as isolated rows can, in principle, produce that missing
causal structure — a payment fails *because* the agent's balance was low
*because* their salary hadn't landed yet, not because a row said so.
That's the hypothesis this project tests. It is a hypothesis, not a
foregone conclusion — Phase 1's job is specifically to find out whether
a small, honest version of this actually produces something more useful
than the current generator, before any larger commitment is made.

## Who this is for

Right now: a research/engineering exploration, not a product with
external users. The audience is future work on Heimdall (or a
successor project) that needs richer, causally-structured financial
data than a single static dataset can honestly provide.

## What Phase 1 must deliver (see Phases.md for the full breakdown)

A working, runnable simulation with:
- A handful of agent types (Person, Bank, Merchant) with simple,
  documented behavioral rules — not LLM-driven, not a black box.
- A tick-based or event-based clock that advances the world over
  simulated time.
- Agents that transact with each other based on stated probability
  rules (income arrival, spending, occasional payment failure) —
  every rule's source stated explicitly: research-grounded, a
  reasonable modeling assumption named as such, or a placeholder to
  replace later. No rule pretends to be more authoritative than it is.
- An event log output (structurally similar in spirit to
  `financial_system/data/raw/*.csv` — real files, not an in-memory
  toy) that a downstream system could read.
- Basic descriptive statistics proving the output is a plausible
  transaction history (volume, failure rate, distribution shapes) —
  not a claim that it matches real-world financial data, since no
  calibration against real data happens until a later phase.

## What Phase 1 explicitly does NOT include

- No AML, credit, chargeback, treasury, or markets domains.
- No LLM anywhere in the simulation loop.
- No external dataset downloads.
- No integration with `financial_system/`.
- No training or evaluating ML models.
- No claim that this simulation is realistic, validated, or
  production-grade. It's a first, honest, small proof of the core
  mechanism.

## Success criteria for Phase 1

The simulation runs, produces a real, inspectable event log across a
meaningful population and time span, every behavioral rule's
provenance is stated in `Rules.md`/code comments, and the resulting
statistics are reported honestly — including if the result is "this
doesn't obviously produce richer causal structure than the current
generator," which would itself be a valid, useful finding, not a
failure to hide.
