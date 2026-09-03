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

## Open questions for a future session (as of end of Phase 1)

- The specific transition point (~0.05–0.25 balance/income ratio) is an
  artifact of the current `PURCHASE_FRACTION_RANGE`/`BALANCE_FACTOR_*`
  constants, not a discovered fact — changing those constants would
  predictably shift it. Worth remembering before quoting these exact
  percentages as if they mean something beyond this Phase 1 build.
- Nothing about Phase 2+ (institutional ledgers, retries, Heimdall
  bridge) has been started, per Rules.md #9 — intentionally.

---

# Phase 2 — Institutional depth

## Status: built, run, and tested. Working.

All five docs (PRD, Architecture, Rules, Phases, Design) plus this file
were re-read before touching any code, then the actual Phase 1 code
(`world/models.py`, `world/clock.py`, `world/engine.py`,
`world/agents/*.py`, `run_simulation.py`, `stats/report.py`,
`tests/test_engine.py`) was read in full before writing anything, per
the standing instruction to match Phase 1's existing conventions rather
than reinvent them.

Scope, per Phases.md's Phase 2 line: "Real double-entry-style ledger for
Bank (assets/liabilities, not just a balance number), an Account
registry, basic settlement between Merchant and Bank." Nothing beyond
that was built — no AML, no credit scoring, no refunds/chargebacks, no
retries (all explicitly Phase 3+/4 territory), no touching
`financial_system/`, no LLM, no external dataset.

## What changed

```
world/models.py       LedgerEntry: now has entry_type (debit/credit),
                       unsigned amount, and transaction_id (was: one
                       signed amount, no linkage). Account/Transaction/
                       Event structurally unchanged (Account gains new
                       owner_type values; Transaction gains one new kind
                       value, "settlement" -- no field changes).
world/agents/bank.py   Rewritten. Bank.credit()/debit() (single-entry)
                       are GONE, replaced by Bank.fund_external() and
                       the module-level post_transfer() function, both
                       of which always post a balanced debit+credit
                       pair. New Bank.open_reserve_account() creates one
                       asset-side "bank_reserve" account per Bank.
world/agents/merchant.py  Merchant gains `pending_account_id` -- a
                       second bank account holding proceeds received
                       but not yet settled.
world/engine.py        _build_world creates a reserve account per Bank
                       and a pending account per Merchant. _maybe_pay_
                       income/_maybe_attempt_purchase now call
                       fund_external/post_transfer instead of credit/
                       debit. New _run_settlement() sweeps pending ->
                       settled once per day, before that day's Person
                       loop. _record() now takes a caller-supplied
                       transaction_id (needed so ledger entries can be
                       linked to it) instead of generating one itself.
run_simulation.py      Writes a new ledger_entries.csv (every
                       LedgerEntry, flattened across every account,
                       sorted by entry_id for determinism). merchants.csv
                       gains pending_account_id/pending_balance columns.
tests/test_engine.py   One test (test_transaction_fields_well_formed)
                       extended with a `settlement` branch; one test
                       (the byte-identical-CSV determinism test) extended
                       to also diff ledger_entries.csv. Nothing else
                       touched -- all 9 original tests still pass
                       unmodified in behavior.
tests/test_ledger.py   NEW. 15 tests, all Phase 2-specific (see Testing
                       below).
docs/Phases.md         Phase 2's status line updated NOT STARTED -> DONE
                       with a one-paragraph summary, in the existing
                       style.
docs/Memory.md         This section.
```

`docs/PRD.md`, `docs/Architecture.md`, and `docs/Rules.md` were NOT
modified — no factual inconsistency was found in them during this work.

## Key design decisions and why

- **A `bank_reserve` asset account per Bank, not a signed/negative-
  capable interbank clearing account.** Real double-entry bookkeeping
  needs an asset side to balance liability-side inflows (salary):
  crediting a Person's deposit liability without a matching debit
  somewhere would just be Phase 1's single-entry ledger again. The
  reserve account is that debit target. It is *only ever debited
  (increased)* by `fund_external()` — nothing in Phase 2's scope draws
  it down (no cash withdrawal, no bank failure modeled) — so it is
  monotonically non-decreasing and can never go negative by
  construction, not by a special-cased exemption from the "no negative
  balances" rule. This was a deliberate choice over the alternative
  (a per-bank interbank *clearing* account that could carry a negative
  net position under real correspondent-banking semantics), specifically
  because that alternative would conflict with this task's explicit "no
  negative balances anywhere, including inside the new ledger" bar. See
  `world/agents/bank.py`'s module docstring for the full reasoning.

- **Cross-bank transfers are posted as one direct balanced pair, not
  routed through any interbank settlement mechanism.** A Person's bank
  and a Merchant's bank are chosen independently at world-generation
  time (unchanged from Phase 1), so most purchases move money between
  two different `Bank` agents. Modeling real interbank settlement
  (nostro/vostro accounts, net settlement batches, correspondent
  banking) honestly would need exactly the negative-capable clearing
  account ruled out above. Instead, `post_transfer()` (a module-level
  function, not a `Bank` method, specifically so it can post into two
  different banks' account dicts) debits the source and credits the
  destination directly, as if every `Bank` agent shared one clearing
  ledger. **This is a named simplification, not a hidden one** — the
  global double-entry invariant ("debits == credits across the whole
  ledger") holds exactly because of this choice, but it means Phase 2's
  "Bank" agents don't yet have fully independent, individually-
  reconcilable balance sheets against each other; only the whole
  simulated banking system's ledger is guaranteed to balance. A real
  interbank layer is a reasonable Phase 3+/5 candidate, not attempted
  here.

- **Opening balances stay outside the ledger's scope, exactly as in
  Phase 1.** A Person's opening balance is still seeded directly onto
  `Account.balance` with zero matching ledger entries — unchanged
  behavior from Phase 1's `Bank.open_account()`. This was a deliberate
  choice against inventing a synthetic "bootstrap funding" transaction
  (which would have been easy to add: Debit reserve / Credit account,
  same as salary) because Phase 1 never had one, this task didn't ask
  for one, and world-generation initial conditions are conceptually
  different from a simulated transaction. Net effect: the double-entry
  invariant is proven over the *ledger* (i.e., over modeled economic
  events from day 0 onward), not over total system balances including
  initial seeding — stated explicitly here and in code so nobody
  mistakes the invariant for "total money in = total money out from
  absolute zero."

- **`LedgerEntry.amount` changed from signed to unsigned, with a new
  `entry_type` field.** Phase 1 stored `+amount` for credit, `-amount`
  for debit, on a per-account single-entry basis. Phase 2 needed
  entries to be explicitly typed and pairable (for the invariant check
  and for the `transaction_id` linkage) — unsigned amount + explicit
  `entry_type` is the standard double-entry convention and avoids sign-
  convention ambiguity between the two different balance-sheet sides
  (asset vs. liability) that now coexist in one ledger. This is a
  breaking schema change to `LedgerEntry` (not to `Transaction`/`Event`,
  which are structurally unchanged apart from one new `kind` value), but
  nothing outside `world/agents/bank.py` and `world/engine.py` read
  `LedgerEntry.amount`'s sign in Phase 1, so the blast radius was
  checked (grep) and confirmed contained.

- **Settlement is a full daily sweep, at a fixed time, drawing no RNG.**
  Every day, before that day's Person loop runs, every Merchant's entire
  pending balance (if any) moves to their settled account in one
  operation. Because purchases can only add to a pending account *after*
  the sweep that day already ran, whatever a sweep finds is exactly
  yesterday's (and only yesterday's) proceeds — this makes "full sweep,
  once a day, first thing" mechanically equivalent to "T+1", without
  needing to track per-day sub-balances explicitly. The sweep's
  timestamp is fixed (03:00 UTC) rather than RNG-sampled like per-person
  event timestamps are, because settlement is modeled as a systemic
  batch process, not an individual agent's probabilistic decision — this
  also means adding settlement did not perturb the RNG draw sequence
  that determines purchase/salary outcomes, keeping Phase 2's numerical
  differences from a hypothetical unmodified Phase 1 run limited to "new
  settlement rows exist," not "unrelated purchase outcomes silently
  shifted because of new RNG consumption."

- **T+1, not same-day, chosen for the settlement delay (provenance:
  MODELING ASSUMPTION).** Stated inline in `world/engine.py`'s
  `_run_settlement` docstring. Not calibrated to any specific real card
  network or processor — chosen because (a) it needed to be non-zero for
  "received" and "settled" to be genuinely distinct states, which is the
  entire point of this Phase 2 feature per the task brief ("rather than
  money just appearing usable instantly"), and (b) T+1 is a simple,
  auditable rule matching the general shape of real card-payment
  settlement cycles (commonly 1-2 business days) without claiming that
  specific precision. A same-day (same-tick) rule was considered and
  rejected specifically because it wouldn't produce any observable
  received-vs-settled distinction in the output at all.

- **The last simulated day's purchase proceeds are never settled.**
  Because the sweep runs at the *start* of each day, there is no "day
  `num_days`" tick to sweep the final day's proceeds on. Left this way
  deliberately rather than adding an end-of-run "settle everything"
  step: a real business genuinely always has some in-flight
  receivables, so an always-nonzero final pending balance is realistic,
  not a leak — and adding a special end-of-run sweep would have been an
  inconsistent, same-day exception to the T+1 rule applied everywhere
  else. `tests/test_ledger.py::test_final_day_purchases_remain_
  unsettled_at_run_end` proves this is real, current behavior (not
  merely a claim), specifically so a future accidental "fix" that added
  an end-of-run sweep would be caught by a failing test, not silently
  ship as an undocumented behavior change.

- **`settlement` added as a new `Transaction.kind` value, `pending:<id>`
  added as a new synthetic `from_id` prefix.** Mirrors Phase 1's already-
  established `employer:<id>` convention exactly (a synthetic,
  unmodeled counterparty id for a money movement that doesn't have a
  real modeled agent on one side) rather than inventing a different
  pattern. This is the one place Phase 2 extends the `kind` taxonomy;
  Rules.md #9 ("don't build Phase 2+ material without it being
  explicitly requested") does not apply here since Phase 2 itself is
  explicitly what's being built, and "basic settlement between Merchant
  and Bank" is its literal, stated scope.

- **`_record()` now takes a caller-generated `transaction_id`, rather
  than generating one internally.** Needed because `LedgerEntry.
  transaction_id` has to reference the same id the `Transaction` row
  will end up with, and the ledger posting (`fund_external`/
  `post_transfer`) happens before `_record()` is called (so the
  Transaction/Event can correctly reflect whether the transfer
  succeeded). Callers now do `txn_id = self.ids.next_txn_id()` up front
  and pass it through both calls.

## Provenance of every new rule (Rules.md #2)

| Rule | Value | Provenance |
|---|---|---|
| Settlement delay | Exactly 1 simulated day (T+1), full daily sweep | Modeling assumption — named stand-in for real card-network settlement cycles (commonly ~1-2 business days), not calibrated to any specific processor; chosen non-zero specifically so "received" and "settled" are observably distinct states, which is this feature's whole purpose |
| Settlement batch time | Fixed 03:00 UTC, not RNG-sampled | Modeling assumption — settlement is a systemic batch process, not an individual agent's probabilistic decision, so it is modeled as deterministic and RNG-free, unlike per-person event timestamps |
| Cross-bank transfer mechanics | Direct balanced pair, no interbank clearing account modeled | Modeling assumption / explicit scope simplification — real interbank settlement (nostro/vostro, net settlement batches) is not attempted; stated plainly as a scope boundary, not hidden |
| Opening balance funding | No matching ledger entries (unchanged from Phase 1) | Modeling assumption — world-generation initial condition, not a simulated transaction; the double-entry invariant is proven over the ledger (modeled events), not over total system balances from absolute zero |
| Bank reserve account | One per Bank, asset-side, monotonically non-decreasing | Modeling assumption — the double-entry counterpart for external (salary) inflows; never drawn down because no cash withdrawal is modeled in Phase 2's scope |

## Testing — what's actually verified, not just claimed

`tests/test_ledger.py`, 15 new tests, all passing (24 total across both
test files as of this session):

- **Global double-entry invariant**: sum of every debit-entry amount
  across every account in every bank equals the sum of every credit-
  entry amount, exactly, at the end of a run
  (`test_double_entry_invariant_holds_globally`).
- **Per-transaction double-entry invariant** (stronger than the global
  check — rules out an aggregate check hiding an offsetting pair of
  unrelated imbalances): for every individual `transaction_id`, its own
  debit and credit entries balance, and there are exactly two entries
  per ledger-backed transaction, never more or fewer
  (`test_double_entry_invariant_holds_per_transaction`).
- **Traceability**: every `LedgerEntry.transaction_id` resolves to a
  real `Transaction`; every `payment_failure` transaction corresponds to
  *zero* ledger entries anywhere (no partial/phantom postings on a
  failed payment).
- **No negative balances anywhere in the new ledger**, extended to cover
  Phase 2's two new account types (`bank_reserve`, `merchant_pending`),
  checked at every single ledger entry, not just final state
  (`test_no_negative_balance_across_all_account_types`) — and the test
  explicitly asserts all four account types were actually exercised, so
  the check isn't vacuous for the new ones.
- **Reserve account correctness**: monotonically non-decreasing across
  its own ledger (proving *why* it can't go negative, not just that it
  didn't); its final balance reconciles exactly against the sum of all
  salary amounts paid, computed independently from `Transaction` rows
  (`test_reserve_account_balance_equals_total_salary_paid`) — a real
  cross-check between two independently-derived numbers, not a
  tautology.
- **Settlement mechanics**: purchase proceeds are proven (via a
  minimal, fully hand-traceable 1-person/1-bank/1-merchant scenario) to
  land in the merchant's PENDING account and NOT their settled account
  on the same day; settlement for a given merchant always lands on
  `purchase_day + 1` exactly, not merely "eventually"
  (`test_settlement_is_exactly_next_day`); the final simulated day's
  proceeds are proven to remain deliberately unsettled at run end.
- **Conservation**: for every merchant, settled balance + pending
  balance at run end equals the total of every successful purchase
  amount they ever received — nothing lost, nothing duplicated
  (`test_merchant_settled_plus_pending_equals_total_purchase_proceeds`).
- **Determinism** extended to the new ledger: same seed → identical
  in-memory `LedgerEntry` sequences across two separate runs; different
  seeds → different ledger output (sanity that settlement/ledger logic
  actually depends on the RNG-driven purchase/salary stream, not
  silently constant).

`tests/test_engine.py`'s original 9 tests all still pass, with two
minimal, additive edits (not behavior changes to old cases):
`test_transaction_fields_well_formed` gained a `settlement`/`pending:`
branch alongside the unchanged `salary`/other branches, and the byte-
identical-CSV determinism test now also diffs `ledger_entries.csv`.

**Manual, end-to-end verification** (per this task's brief, not just
pytest): ran `python run_simulation.py --seed 42 --population 200 --days
60 --outdir output/phase2_check` once, and a second time into
`output/phase2_check_b`; `diff -rq` between the two directories reported
zero differences across all 7 output files (persons/banks/merchants/
accounts/transactions/events/ledger_entries.csv) — full CLI-level
determinism, not just the in-memory/pytest-level check. Also manually
verified on that run's output: 0 negative balances across 233 accounts
and 10,748 ledger entries; global debit total exactly equals global
credit total (4,586,873.56 = 4,586,873.56); 878 settlement transactions
and 878 matching `settlement_completed` events; every merchant's
settled+pending balance reconciles exactly against their total purchase
proceeds (0 mismatches across 15 merchants). Both throwaway output
directories were deleted after (`output/sample/` — Phase 1's committed
sample — was left untouched; regenerating it to reflect Phase 2's new
CSV columns/file was judged out of this task's explicit scope and left
for a reviewer to decide on).

Also ran `stats/report.py` against the phase2_check output before
deleting it — it works unmodified against Phase 2 output, since its
`by_kind` grouping is a generic dict keyed by whatever `kind` values
appear; `settlement` rows show up correctly in the Volume section
without any code change needed there.

## What's genuinely done vs. still rough

**Done and solid**: the double-entry invariant (proven globally and
per-transaction), no-negative-balance across all four account types,
the settlement received→pending→settled state machine and its exact
T+1 timing, full conservation of merchant proceeds, determinism
extended through the new ledger and settlement logic, CLI-level
byte-identical-output verification, 24/24 tests passing.

**Rough / minimal by design (Phase 2 scope, not bugs — named plainly,
per Rules.md #5)**:
- **No real interbank settlement mechanics.** Cross-bank transfers are
  posted as a single direct balanced pair, as if all `Bank` agents
  shared one clearing ledger, rather than modeling nostro/vostro
  accounts or net settlement batches between banks. The global
  double-entry invariant holds; a *per-bank* independent balance sheet
  reconciliation does not yet, and wasn't attempted. See "Key design
  decisions" above.
- **Opening balances are still outside the ledger** (zero matching
  entries), exactly as in Phase 1 — an intentional, stated scope
  boundary, not something Phase 2 was asked to fix.
- **Settlement is a single, uniform, always-applied rule** — every
  merchant, every day, same fixed T+1 delay. No per-merchant variation,
  no minimum settlement amount, no batching/fees, no settlement
  failures (a settlement transfer can never itself fail, since it only
  ever moves exactly a pending account's own current balance, which by
  definition it can always cover). Real payment processors vary
  settlement timing by merchant risk tier, payment method, and country
  — none of that is modeled, and wasn't asked for.
- **The `balance_before` field on a settlement `Transaction` is close
  to tautological** — because settlement always sweeps the *entire*
  pending balance, `balance_before` (the pending account's balance right
  before the sweep) always exactly equals `amount` (the amount swept).
  Kept anyway for schema consistency with every other `Transaction`
  kind and because it's still directly meaningful (it's not computed
  FROM `amount`, it's independently read from account state before the
  transfer) — same honesty standard Phase 1 already applied to
  `payment_failure`'s analogous near-tautological check.
- **No AML, credit scoring, refunds/chargebacks, retries** — untouched,
  exactly as instructed; those remain Phase 3+/4 territory.
- **`output/sample/` (the committed Phase 1 example run) was not
  regenerated** to reflect Phase 2's new `ledger_entries.csv` file and
  `merchants.csv` columns — this wasn't explicitly requested, and
  updating a previously-reviewed committed artifact felt like a
  decision for a reviewer, not something to do unasked. It currently
  reflects Phase 1's schema only; a future session should regenerate it
  if Phase 2's output shape should be the new reference sample.

## Open questions for a future session

- Whether a real interbank settlement layer (the "Rough" item above) is
  worth building is an open question for whenever multi-bank realism
  actually matters to a downstream use of this project — not assumed to
  be needed.
- Whether `output/sample/` should be regenerated against Phase 2's
  output shape is an open, deliberately-left decision (see above).
- Nothing about Phase 3+ (behavioral realism, domain events, scale,
  Heimdall bridge) has been started, per Rules.md #9 — intentionally.

---

# Research + Phase 3 (bounded) — 2026-09-03/04

## Status: research done and written up in full; ONE narrow, cited code
change made; Phase 3 as a whole (full behavioral-realism swap) is NOT
complete — this was an explicitly bounded "research + narrow,
cited implementation" task, not a full Phase 3. `Phases.md`'s Phase 3
line was deliberately left as "NOT STARTED" rather than marked done, to
avoid overclaiming; see "What's genuinely done vs. not" below.

All five docs (PRD, Architecture, Rules, Phases, this file) were re-read
in full before starting, plus the actual code
(`world/models.py`, `world/engine.py`, `world/agents/*.py`,
`run_simulation.py`). Baseline confirmed first: 24/24 tests passing
before any change was made.

## What was researched (full detail in `Simulation/docs/Research.md`)

Five areas, per the task brief: (1) income/spending distributions, (2)
payment fraud rates and risk factors, (3) credit scoring dynamics, (4)
loan interest rate mechanics, (5) bank reserve/liquidity behavior. Used
WebSearch/WebFetch against public sources only (Federal Reserve Board,
regional Feds — Kansas City, New York, Philadelphia, Dallas, San
Francisco — BLS, FRED, Stripe's own public documentation, and named
academic papers) — this specific task had explicit user approval to
consult real research per the task brief (Rules.md #3's "external
dataset downloads" bar still applies and was respected: nothing was
bulk-downloaded, only published summary statistics were cited — see
Research.md's "What was not downloaded, and why").

**A genuine environment limitation surfaced during this work**: this
session's WebFetch tool could not extract text from several PDF sources
(Federal Reserve, NBER, arXiv PDFs all came back as unparsed binary/
stream data) — apparently a PDF-text-extraction limitation of this
environment. Findings resting on such a PDF are flagged in Research.md
as coming from WebSearch's synthesized summary rather than a firsthand
verified quote, and were treated as weaker evidence accordingly (see
next section — this is *why* several tempting-looking numbers were
deliberately not adopted into code).

## What changed in code (exactly one change)

`Simulation/world/engine.py`, `SimulationEngine._run_settlement`'s
docstring: the T+1 settlement-delay rule's provenance was upgraded from
a bare "MODELING ASSUMPTION" to "RESEARCH-GROUNDED, WITH A NAMED
SIMPLIFICATION," citing Stripe's own public documentation ("settlement
typically takes one to three business days after the transaction") plus
corroborating industry sources, for the *qualitative* fact that real
card settlement is genuinely delayed on a roughly 1-3 business day
scale. **The VALUE was not changed** — it's still exactly T+1, still
fixed (not RNG-sampled), still drawing zero randomness — because T+1
already sits inside the cited real range (at its low/conservative end),
and widening it to a random 1-3 day draw would have perturbed the RNG
draw sequence for purchases/salary that Phase 2 deliberately protected
(see this file's Phase 2 section), which this one citation didn't by
itself justify changing. Net effect on simulation output: **zero** —
this is a comment-only change, confirmed by the determinism check below
still passing identically to the pre-change baseline behavior.

## What was deliberately NOT changed, and why (the more important part)

Three other parameters were explicitly eligible for a cited swap per the
task brief (income distribution shape/params, base daily spend
probability, opening-balance fraction) and none were changed:

- **Income distribution** (`INCOME_LOGNORMAL_MU`/`_SIGMA`): the
  log-normal shape is already about as well-supported as real income-
  distribution literature gets for the non-tail population (confirmed,
  didn't need changing). A specific `sigma≈0.5` figure from a
  wage-inequality paper's WebSearch-summarized abstract coincided almost
  exactly with the existing constant — deliberately NOT adopted because
  (a) the source PDF couldn't be independently verified (the
  PDF-extraction limitation above) and (b) "wage dispersion among
  employed workers" isn't quite the same population as "all persons'
  income." Adopting a suspiciously-convenient unverified number is
  exactly the failure mode Rules.md #2 exists to prevent.
- **Base daily spend probability** (`BASE_DAILY_SPEND_PROB = 0.35`): the
  Fed's Diary of Consumer Payment Choice looked like the single most
  promising lead (a widely-cited, real annual survey with a plausible
  "share of consumers making zero payments on a given day" statistic
  that would suggest a higher base rate) — but that specific figure
  could not be verified against any primary source this session could
  actually read (every DCPC PDF fetched came back unparseable), and even
  if verified, DCPC counts ALL payments (bills, rent, transfers), not
  specifically *discretionary* purchases, which is what this constant
  models — a real definitional gap on top of the verification problem.
  Left unchanged; flagged in Research.md as a real lead worth revisiting
  with better tooling.
- **Opening balance fraction** (`OPENING_BALANCE_FRACTION_RANGE = (0.1,
  1.0)`): Fed SHED survey data (63% could cover a $400 expense in cash,
  55% have a 3-month emergency fund) is real and directly fetched, and
  broadly *consistent* with the current wide uniform range — but it's a
  point-in-time adequacy statistic, not a distributional shape/range for
  "opening balance as a fraction of monthly income," so there was no
  clean number to substitute in. Left unchanged.

A fourth, structural (non-swappable) finding is worth naming here too:
BLS Consumer Expenditure Survey data shows spend-as-a-share-of-income
declining as income rises (poorer households spend ≥100% of income;
richer households save more) — a real pattern this simulation's
`purchase_amount()` doesn't capture, since it draws purchase size as the
same fractional range of a person's OWN income regardless of income
level. Fixing this honestly would require making purchase-amount-as-
income-fraction itself a function of income level (a new mechanism, not
a constant swap), which is why it wasn't done here — recorded in
Research.md as a legitimate target for a future, properly-scoped Phase 3
continuation.

## Testing — what's actually verified for this session's change

- `python -m pytest tests/ -v` — ran BEFORE any change (baseline: 24/24
  passing) and AFTER the one docstring edit (24/24 passing, identical —
  expected, since the change touches no executable logic, only a
  docstring).
- Determinism: `python run_simulation.py --seed 42 --population 200
  --days 60 --outdir output/research_check_a` and `..._check_b`, then
  `diff -rq` between them — zero differences (exit code 0). Both
  throwaway directories deleted afterward; `output/sample/` untouched.

## Part C — proposed-only future mechanisms (design, not code)

Written up in full in `Research.md`'s Part C, each grounded in Part A's
actual numbers, not invented: fraud (calibration target: 17.6 basis
points of transaction value, Kansas City Fed 2023 data, up from 7.8bps
in 2011; risk signals: transaction amount + velocity, cited to
Bhattacharyya et al. 2011 and Dal Pozzolo et al. 2017/2018), credit
scoring (initial distribution seeded from the Fed's 2007 Report to
Congress; delinquency-transition-rate targets from FRBNY's Q1 2026
report, 1.48%-7.10% depending on debt type), and loans (rate = base +
risk-spread structure per the Fed's own Sept 2025 FEDS Note, with a
citable spread elasticity of ~5bps/100bps regional default risk for
unsecured credit vs. ~30bps for mortgages; base-rate plausibility range
8.73%-19.21% from G.19's 24-month personal loan series). Each proposal
also names why it's NOT built now — every one of the three needs new
persistent agent state or a new causal object (account compromise for
fraud; score as non-ledger-reconciled state for credit; a new
liability-side `Loan` object with lending-capacity questions Phase 2's
double-entry design never addressed) that's a real architectural
decision deserving its own dedicated, reviewed effort, not something to
bolt on inside a narrow research task. One correction worth flagging for
whoever eventually builds C.3 (loans): a naive "add a bank reserve-ratio
constraint" design would be factually backwards for a present-day
simulation, since the Fed reduced reserve requirements to 0% for all
depository institutions in March 2020 (Research.md Part A §5) — any
future lending-capacity constraint should be modeled on Basel/LCR-style
capital adequacy concepts instead.

## Honest caveats for a future session

- The PDF-extraction limitation (WebFetch returning unparsed binary for
  Fed/NBER/arXiv PDFs in this environment) is worth checking again in a
  future session — several genuinely promising leads (the DCPC
  zero-payment-day statistic in particular) were left unused specifically
  because this session couldn't independently verify them, not because
  they're wrong. A session with working PDF extraction (or with the
  ability to fetch an HTML-rendered version of the same report) could
  plausibly turn at least one of these into a real, defensible Part B
  change.
- `Phases.md`'s Phase 3 line was deliberately NOT updated to "DONE" —
  this session did the *research* half of Phase 3 thoroughly, but made
  only one narrow, low-stakes code change, not the full "replace
  Phase 1's placeholder rules with research-grounded ones" Phase 3
  describes. Marking it done would overclaim; a future session doing
  more of Phase 3's actual constant-swapping work should update that
  line when it's genuinely earned.
- Nothing in `financial_system/` was touched. No LLM calls were added
  anywhere. No dataset was bulk-downloaded (see Research.md's "What was
  not downloaded, and why" for the specific reasoning on each dataset
  that was considered and rejected for direct download). Fraud/credit/
  loan mechanisms remain entirely unimplemented — Part C is design-only,
  per this task's explicit instruction.
