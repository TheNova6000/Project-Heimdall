# Architecture — Financial World Simulation

## Guiding principle

Deterministic + probabilistic agent rules, not an LLM. The whole point
of this project (per the conversation that spawned it) is a simulation
engine that's cheap, fast, reproducible, and inspectable — an LLM in
the simulation loop would defeat all four properties. Discovery.AI-style
reasoning stays a *consumer* of this world's output (investigating
anomalies within it), never a generator of the world itself.

## Phase 1 folder structure

```
Simulation/
├── docs/                    PRD.md, Architecture.md (this file),
│                             Rules.md, Phases.md, Design.md,
│                             Memory.md (created once building starts)
├── world/
│   ├── agents/
│   │   ├── person.py         Person agent: income/spend/balance rules
│   │   ├── bank.py            Bank agent: accounts, basic ledger
│   │   └── merchant.py        Merchant agent: sales, basic ledger
│   ├── clock.py                Simulation time-step driver
│   ├── engine.py                Ties agents + clock into one run
│   └── models.py                 Typed records: Account, Transaction, Event
├── output/                    Generated event logs land here (gitignored
│                             except a small committed sample)
├── stats/
│   └── report.py                Post-run descriptive statistics
├── run_simulation.py           Entry point: `python run_simulation.py`
└── tests/
    └── test_engine.py           Basic sanity tests (determinism given a
                                seed, no negative balances, event log
                                well-formed)
```

## Core data model (Phase 1 scope only)

```
Person
  person_id, name, income_monthly, balance, risk_preference (0-1)

Bank
  bank_id, name
  Account
    account_id, owner_id (Person), balance, ledger: list[LedgerEntry]

Merchant
  merchant_id, name, bank_account_id

Transaction (the unit of output)
  transaction_id, timestamp, from_id, to_id, amount, kind
  (kind ∈ {salary, purchase, payment_failure, ...} — extend as Phase 1
   actually needs, don't pre-build a taxonomy nobody uses yet)

Event  (append-only, mirrors Heimdall's event-sourcing discipline)
  event_id, event_type, subject_id, occurred_at, payload
```

## Simulation loop (Phase 1)

```
for each tick (e.g. one simulated day):
    for each Person:
        maybe receive income (probability + rule, stated in Rules.md)
        maybe attempt a purchase (probability depends on balance,
            income_monthly, risk_preference -- simple, explicit
            function, not a black box)
        if a purchase is attempted and balance is insufficient:
            emit a payment_failure event (this is where the causal
            link the current Heimdall generator lacks should emerge
            naturally: fails BECAUSE balance was low, not because a
            row was labeled that way)
    write all events/transactions for this tick to the event log
```

No hidden global state. Every agent decision is a function of that
agent's own visible state plus documented probabilities — this keeps
the system inspectable and matches the temporal-honesty lesson from
Heimdall's own Block 5 (an agent's decision must depend only on what
it could actually know, not global truth).

## Tech stack

Python (matches the rest of this repo — no reason to introduce a
second language for a Phase 1 prototype). Plain stdlib + `random` for
probability sampling to start; no new heavy dependencies until a real
need appears. Output as CSV/JSON, matching the plain, inspectable
style of `financial_system/data/raw/`.

## Explicit non-goals for Phase 1 architecture

- No microservices, no database beyond flat files, no web API.
- No plugin/domain-extension system yet (that's Program/Phase-6+
  territory from the larger roadmap in project memory — don't
  pre-build abstraction for phases that don't exist yet).
