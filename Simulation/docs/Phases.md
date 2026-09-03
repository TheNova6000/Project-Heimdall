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

## Phase 2 — Institutional depth (NOT STARTED)

Real double-entry-style ledger for Bank (assets/liabilities, not just
a balance number), an Account registry, basic settlement between
Merchant and Bank. Only begins after Phase 1 is done and reviewed.

## Phase 3 — Behavioral realism (NOT STARTED)

Replace Phase 1's placeholder/assumption-labeled probability rules
with research-grounded ones where real sources exist (income
distributions, spending patterns) — each swap cited, not assumed.

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
