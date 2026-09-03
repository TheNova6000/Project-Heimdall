# Rules — Financial World Simulation

These are hard boundaries for anyone (human or agent) building this
project. They exist because this whole initiative grew out of a much
larger conversation where the exact opposite of several of these rules
was tried and correctly rejected — read this as "why," not just "what."

## 1. No LLM in the simulation loop

Agent decisions (does this Person spend, does this payment fail, etc.)
must come from explicit, readable probability functions — not a model
call. This is a stated project goal, not just a cost-saving measure:
the simulation needs to be fast, deterministic-given-a-seed, and
auditable. Discovery.AI-style reasoning may later *investigate* this
world's output, but never *generates* it.

## 2. Every behavioral rule states its own provenance

For every probability or rule (income arrival chance, spend
probability, failure probability, whatever comes next), the code
comment or `Rules.md` entry must say one of:
- **Research-grounded** — cite the source.
- **Modeling assumption** — state it's a deliberate simplification and
  why it's reasonable, not pretend it's empirically derived.
- **Placeholder** — explicitly marked TODO, not left silently looking
  authoritative.

This is the single most important carried-over lesson from Heimdall:
a project that spent a full session distinguishing "we proved this
empirically" from "this is an assumption" should not casually blur
that line the moment it starts generating its own data.

## 3. No external dataset downloads without explicit user approval

Phase 1 does not need external data at all — it generates its own
world. If a later phase genuinely needs a real dataset (for
calibration, say), that is a new decision to bring back to the user
explicitly, not something to do proactively because it seemed useful.

## 4. Do not touch `financial_system/` in Phase 1

This is a separate, isolated project. `financial_system/` is a locked,
submitted, tested codebase — nothing here imports from it, writes to
it, or assumes it exists. If a later phase proposes an actual bridge
between the two, that's an explicit, reviewed decision, not something
that happens by accident because a path was convenient.

## 5. Small, real, and honestly reported over large and impressive-sounding

Phase 1's job is to test whether this approach is worth investing
further in — not to look finished. If the simulation's output turns
out to be no richer than the existing generator, that is a valid,
reportable Phase 1 outcome, not a reason to quietly inflate the
behavioral model until it looks better.

## 6. Determinism

Given the same random seed, the simulation must produce the exact
same output. This is testable and must be tested (see
`tests/test_engine.py`). No wall-clock time, no unseeded randomness
anywhere in the core loop.

## 7. No negative balances, no fabricated money

An agent cannot spend money it doesn't have — that's the entire
mechanism this project exists to get right (a payment fails *because*
of insufficient balance, not despite it). If a Person's balance can go
negative silently, the whole causal-structure premise is broken; treat
it as a bug, not an edge case to shrug off.

## 8. Keep `Memory.md`

Once building actually starts, create and maintain
`Simulation/docs/Memory.md` — what's built, what's decided, what's
still open — so a future session (human or agent) picking this up
doesn't have to re-read every file or guess at prior decisions.
Update it as you go, not as an afterthought at the end.

## 9. Stay inside Phase 1's scope

`Phases.md` lists what comes after Phase 1. Do not start building
Phase 2+ material (institutions beyond Bank/Merchant, AML, credit,
research ingestion, etc.) without it being explicitly requested. A
completed, honestly-reported Phase 1 is the deliverable, not a partial
version of everything.
