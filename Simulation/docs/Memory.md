# Memory — Financial World Simulation

Living document (Rules.md #8). Written as Phase 1 was built, not
reconstructed afterward. Read this before touching the code again.

## Status: Phase 1 built, run, and tested. Working.

All five planning docs (PRD, Architecture, Rules, Phases, Design) were
read before any code was written, and Phase 1 was built to match them
literally where they specified something concrete.

## What exists

```
Simulation/
├── docs/            PRD.md, Architecture.md, Rules.md, Phases.md,
│                     Design.md (all pre-existing), Memory.md (this file)
├── world/
│   ├── models.py      LedgerEntry, Account, Transaction, Event (dataclasses)
│   ├── clock.py        SimClock -- tick = 1 simulated day, no wall-clock reads
│   ├── engine.py         SimulationEngine -- world generation + the day loop
│   └── agents/
│       ├── person.py    income/spend/purchase-amount rules
│       ├── bank.py       accounts + credit/debit (debit is the ONE place
│       │                 that enforces "no negative balance")
│       └── merchant.py   passive sales recipient, no Phase 1 behavior
├── run_simulation.py    CLI entry point, writes CSVs
├── stats/report.py       descriptive stats + the causal-structure check
├── tests/test_engine.py  9 pytest tests, all passing
├── output/sample/         small COMMITTED sample run (seed=1, 25 persons,
│                          14 days, 107 transactions) + its report.md
└── .gitignore             ignores output/* except output/sample/
```

## How to run it

```
cd Simulation
python run_simulation.py --seed 42 --population 500 --days 120 --outdir output/run_a
python stats/report.py --outdir output/run_a --save output/run_a/report.md
python -m pytest tests/ -v
```

Full CLI options: `--seed --population --banks --merchants --days
--start-date --outdir` (see run_simulation.py `main()`).

## Key design decisions

- **Dataclasses, not Pydantic** (Design.md left this open, "pick one and
  stay consistent") -- Phase 1 has no validation/serialization need that
  justifies the dependency.
- **One `random.Random(seed)` instance per run**, created in
  `SimulationEngine.__init__` and threaded through every call that needs
  randomness. Nothing else calls the global `random` module or reads
  wall-clock time. This is what makes determinism (Rules.md #6) hold —
  verified, not just claimed (see Testing below).
- **Bank.Account.balance is the single source of truth** for a person's
  or merchant's money. `Person.balance` and `Merchant` carry no live
  balance of their own after world-build — `run_simulation.py`'s
  `write_output()` reads final balances back out of the Bank accounts
  when writing `persons.csv`/`merchants.csv`.
- **Salary's `from_id` is a synthetic `employer:<person_id>`**, not a
  modeled agent. Phase 1 has no Employer institution (Architecture.md
  scopes agents to Person/Bank/Merchant only), so income has to enter the
  closed system from somewhere unmodeled. This is a deliberate, standard
  convention for a closed-population toy economy, not the "fabricated
  money" Rules.md #7 warns against — that rule is about money appearing
  mid-transaction between modeled agents (e.g. a credit happening despite
  a debit failing), which never happens here: `bank.debit` and
  `bank.credit` are both idempotent, all-or-nothing operations.
- **Transaction.kind follows Architecture.md literally**: `salary`,
  `purchase`, `payment_failure` — a failed purchase attempt is its own
  transaction kind, not a `purchase` row with a status field.
- **Added `balance_before` to Transaction** beyond Architecture's minimal
  field list — the single most direct, auditable evidence for or against
  the project's central hypothesis. Justified in models.py's docstring;
  not a taxonomy expansion (Rules.md #9 concern), just instrumentation.
- **IDs are sequential counters formatted as 8-hex-char strings**
  (`txn_00000001`, `evt_00000001`, ...) rather than true random UUIDs.
  Matches Design.md's stated shape (`txn_<uuid8>`) while staying trivially
  deterministic — no need to burn RNG draws on ID generation.
- **Event payloads are `json.dumps(..., sort_keys=True)`** — sorted keys
  specifically so identical runs produce byte-identical CSV rows (dict
  key order is not itself guaranteed stable across code paths otherwise).

## Provenance of every probability/rule (Rules.md #2)

All stated inline as code comments at point of use; summarized here for
convenience. None are research-grounded in the "cited empirical study"
sense — Phase 1's job was to prove the mechanism, not calibrate it
(Phases.md Phase 3 is where cited replacements belong).

| Rule | Value | Provenance |
|---|---|---|
| Payday | 1 fixed day/month per person, uniform 1-28 | Modeling assumption — real payroll cadence varies; simplification for a believable income cycle |
| Income noise | ±5% of nominal monthly income | Modeling assumption — named simplification, not a payroll statistic |
| Income level | log-normal(mu=8.3, sigma=0.5), clamped [300, 25000] | Modeling assumption, informally motivated by the standard stylized fact that incomes are approximately log-normal (Aitchison & Brown 1957) — shape only, not calibrated to any dataset |
| Opening balance | uniform(0.1, 1.0) × income_monthly | Modeling assumption — arbitrary but named starting condition |
| risk_preference | uniform(0, 1) | Modeling assumption — least-assumption-laden distribution for an undefined-distribution trait |
| Base daily spend probability | 0.35 | Modeling assumption — order-of-magnitude guess (~1 purchase attempt per 3 days) |
| Risk multiplier on spend prob | 0.7x (risk=0) .. 1.6x (risk=1) | Modeling assumption — named range, not fit to data |
| Balance factor on spend prob | 0.5x (broke) .. 1.0x (balance ≥ 1 month income) | Modeling assumption — the specific mechanism connecting a person's own balance to their own behavior; never drops to 0 (people still try to spend when low on cash, which is what should occasionally fail) |
| Purchase amount | income × uniform(0.005,0.12) × uniform(0.6,1.6) | Modeling assumption — right-skewed shape, not a merchant-spend dataset |
| Merchant category | uniform random pick from a fixed 5-item list | Placeholder — cosmetic label only, no behavioral effect |
| Event time-of-day | uniform in [7:00, 22:59] UTC | Modeling assumption — exists only so same-day events get distinct timestamps; no claim about real payment timing |

## Testing — what's actually verified, not just claimed

`tests/test_engine.py`, 9 tests, all passing as of this session:
- **Determinism**: same seed → identical in-memory Transaction/Event
  lists (`test_same_seed_produces_identical_transactions_in_memory`) AND
  byte-identical CSV files across two full separate runs via `filecmp.cmp`
  (`test_same_seed_produces_byte_identical_csv_output`). Also checked
  manually outside pytest: ran `run_simulation.py --seed 42 --population
  500 --days 120` twice into `output/run_a` and `output/run_b`, then
  `diff -rq` — zero differences, exit code 0. (Those two run_a/run_b dirs
  were deleted after — they're the disposable large-scale confirmation,
  `output/sample/` is the one kept.)
- **Different seeds → different output** (sanity check the RNG is
  actually being used, not silently ignored).
- **No negative balances**: checked on final balances AND on every single
  ledger entry's `balance_after` across the whole run, not just the end
  state.
- **payment_failure rows never move money and always have
  `balance_before < amount`** — the mechanical proof of the causal claim.
- **ID uniqueness, 1:1 Transaction:Event correspondence, well-formed
  fields** (positive amounts, valid `kind`, resolvable `from_id`/`to_id`,
  parseable ISO timestamps), and CSV round-trip parseability.

## The actual research finding (honest, per Rules.md #5)

Ran seed=42, 500 persons, 3 banks, 15 merchants, 120 days →
24,061 transactions (21,831 purchases, 230 payment_failures, 2,000
salary payments). Failure rate 1.04% of purchase attempts. Zero negative
balances anywhere, ever (checked at every ledger entry, not just at the
end).

**The headline result**: bucketing every purchase attempt by
`balance_before / income_monthly` at the moment of the attempt gives a
clean, monotonic relationship:

| balance/income ratio | attempts | failure rate |
|---|---|---|
| < 0.02 | 80 | 96.25% |
| 0.02–0.05 | 104 | 70.19% |
| 0.05–0.10 | 133 | 45.86% |
| 0.10–0.25 | 517 | 3.68% |
| ≥ 0.25 | 21,227 | 0.00% |

This is real evidence for the PRD's hypothesis: failure risk is a smooth,
inspectable function of an individual agent's own state at that specific
moment, not a flat per-category draw. That is exactly the structure
`financial_system`'s `retry_would_succeed` coin-flip lacks by
construction (confirmed by reading its source, per PRD.md).

**The honest caveat**: bucketing by *income group* instead (below- vs
at/above-median income) shows almost no signal — below-median-income
persons actually failed *less* often (0.94% vs 1.15%) in the 500-person
run. This is because purchase size scales with the buyer's own income
(`purchase_amount` is a fraction of `income_monthly`), so raw income
level is confounded and isn't, by itself, a strong predictor — it's
specifically the *ratio* of balance-to-income at the moment of the
attempt that carries the signal, not income level or balance level
alone. Worth knowing before anyone assumes "low income → high failure"
holds trivially in this simulation; it doesn't, and that's a real,
reportable finding, not a bug (some of it also reflects Phase 1's
minimal behavioral model — there's no rent/bills/debt agent state yet,
so a "low income but currently flush" person and a "high income but
currently drained" person are both possible and both correctly captured
by balance-ratio, just not by income alone).

## What's genuinely done vs. still rough

**Done and solid**: the causal mechanism itself (balance-gated debit),
determinism, no-negative-balance guarantee, CSV output shape, the stats
report's core sections, all 9 tests.

**Rough / minimal by design (Phase 1 scope, not bugs)**:
- Only one purchase attempt considered per person per day (no multi-item
  shopping days). Architecture's pseudocode is written this way too.
- No retry behavior at all — a failed purchase is terminal, never
  retried. That's explicitly Phase 4 (Phases.md).
- Merchants have zero behavior beyond receiving money — no settlement,
  no spending, no failure modes of their own. Explicitly Phase 2 territory.
- No refunds/chargebacks/AML — explicitly out of Phase 1 scope (PRD.md).
- Population generation (income/balance/risk distributions) is IID per
  person with no geography, household, or correlation structure —
  acceptable for Phase 1's "does the mechanism work at all" question, but
  a likely first target if Phase 3 happens.
- `report.py`'s income-group split turned out to be a weak, confounded
  statistic in practice (see above) — kept in the report rather than
  deleted, because showing a statistic that *doesn't* support the
  hypothesis alongside one that does is exactly the "honestly reported"
  standard Rules.md #5 asks for.

## Robustness check across seeds

Re-ran the balance-ratio breakdown at seed=7 and seed=2026 (300 persons,
90 days each, then deleted — not committed) to check the headline finding
wasn't a fluke of seed=42:

| ratio bucket | seed 42 (500p/120d) | seed 7 (300p/90d) | seed 2026 (300p/90d) |
|---|---|---|---|
| < 0.02 | 96.25% | 97.67% | 95.77% |
| 0.02–0.05 | 70.19% | 73.13% | 75.76% |
| 0.05–0.10 | 45.86% | 36.99% | 39.47% |
| 0.10–0.25 | 3.68% | 4.78% | 2.99% |
| ≥ 0.25 | 0.00% | 0.00% | 0.00% |

Same monotonic shape every time, with the transition consistently
sitting between ratio 0.05 and 0.25. This is not a single-seed artifact —
it falls directly out of `purchase_amount()` being capped at ~18% of
monthly income (`PURCHASE_FRACTION_RANGE`/`PURCHASE_FRACTION_JITTER` in
`person.py`), so anyone with balance ≥ ~25% of their income is
mechanically almost unfailable, and anyone under ~2% is mechanically
almost always going to fail their next attempt. That's a direct,
traceable consequence of the stated constants, which is exactly the
auditability property this project is supposed to have — it is not a
statistical accident.

## Open questions for a future session

- The specific transition point (~0.05–0.25 balance/income ratio) is an
  artifact of the current `PURCHASE_FRACTION_RANGE`/`BALANCE_FACTOR_*`
  constants, not a discovered fact — changing those constants would
  predictably shift it. Worth remembering before quoting these exact
  percentages as if they mean something beyond this Phase 1 build.
- Nothing about Phase 2+ (institutional ledgers, retries, Heimdall
  bridge) has been started, per Rules.md #9 — intentionally.
