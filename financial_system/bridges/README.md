# Simulation -> Heimdall bridge (Working Section 23, bounded implementation)

`docs/SIMULATION_ARCHITECTURE_SPEC.md`'s Working Section 23 describes a full
observation-boundary/action-writeback bridge and explicitly does not build
it ("naming what the eventual bridge would need to look like... without
building any of it"). This directory is a narrower, concrete, ADDITIVE-ONLY
slice of that: a real, running one-way bridge that transforms a completed
`Simulation/` run's output into `financial_system/`'s real raw-CSV input
schema, and calls Heimdall's actual, unmodified Phase 1/2/3/Recovery
functions on it. No file under `financial_system/` was edited to build this
-- `git diff --stat financial_system/` is empty; every file listed below is
new.

**No writeback.** This bridge only reads a finished `Simulation/` run and
produces Heimdall decisions; it does not write an Action back into a
running `Simulation/` world (Working Section 23's item (2)/(3) --
`Simulation/` only ever produces a finished CSV export, has no paused/live
world to act into, and has no retry mechanism yet). That remains exactly as
unbuilt as the spec says.

## Why Recovery, not Risk or Controller

Three domains were possible; only one was actually buildable against what
`Simulation/` produces:

- **Risk** (`financial_system/risk/`) needs shared-device fraud-ring
  structure: `risk/runner.py`'s `devices_with_sharers()` only ever produces
  a nonzero score for a Device node with >=2 distinct Customers. `Simulation/`
  has no Device, PaymentInstrument, or fraud concept at all --
  `Simulation/output/*/persons.csv` has no such columns, and nothing in
  `Simulation/world/` models shared devices. A bridge could only ever
  produce one placeholder Device per Person (see "Fabricated fields"
  below), which makes Risk's whole signal structurally vacuous -- not a
  real test of Risk, just zeros.
- **Controller** (settlement reconciliation) needs Settlement and
  BankTransaction records with fee/tax breakdowns matched against bank
  deposits. `Simulation/` has a `settlement` transaction kind (merchant ->
  bank), but it is a single merchant-owned balance movement, not
  Razorpay-shaped per-payment settlement batching with fees -- mapping it
  onto Controller's schema would mean inventing a settlement-batching
  policy Simulation never actually decided, not transforming real signal.
- **Recovery** (`financial_system/recovery/`) needs exactly three things
  per failed Payment (confirmed by reading `recovery/signals.py` directly,
  not guessed): `status`, `failure_reason`, and whether a sibling Payment on
  the same Order already succeeded. `Simulation/`'s `transactions.csv` has
  a `kind` (`purchase` / `payment_failure`) that IS payment status, and its
  one real, mechanically-verified failure cause (`balance_before < amount`)
  maps onto exactly one real Heimdall failure-taxonomy category,
  `insufficient_funds` -- not invented, the one thing `Simulation/` actually
  causally produces (this is also the fact Working Section 24 names as
  `Simulation/`'s "single most defensible" supervised-learning label, for
  the same reason).

Recovery was the only domain where the bridge is a real transform of real
signal, not a structural formality producing meaningless output.

## Field mapping (Simulation -> Heimdall raw CSV)

Simulation output columns are `Simulation/output/*/persons.csv`,
`merchants.csv`, `transactions.csv` (read directly; `Simulation/docs/Design.md`
documents the same shape). Heimdall raw-CSV columns are read from
`financial_system/data/raw/*.csv`'s real headers and
`financial_system/ingestion/*.py`'s real required fields.

| Simulation field | -> | Heimdall field | Notes |
|---|---|---|---|
| `persons.csv: person_id` | -> | `customers.csv: customer_id` | direct |
| `persons.csv: name` | -> | `customers.csv: name` | direct |
| *(none)* | -> | `customers.csv: email` | **fabricated**: `<person_id>@simulation.bridge.local` -- Simulation has no email field |
| *(none)* | -> | `customers.csv: created_at` | **fabricated**: earliest transaction timestamp in the run -- Simulation's Person has no creation date |
| `merchants.csv: merchant_id` | -> | `merchants.csv: merchant_id` | direct |
| `merchants.csv: name` | -> | `merchants.csv: name` | direct |
| `merchants.csv: category` | -> | `merchants.csv: category` | direct |
| *(none)* | -> | `merchants.csv: created_at` | **fabricated**: same earliest-timestamp placeholder |
| *(none)* | -> | `devices.csv` (1 row per Person) | **fabricated, zero signal**: `dev_bridge_<person_id>`, fixed placeholder fingerprint. Simulation has no device concept. `recovery/signals.py` never reads this field -- confirmed by reading it -- so it cannot affect a Recovery decision. It DOES make Risk's device-sharing signal structurally vacuous, which is why Risk was not chosen (see above). |
| *(none)* | -> | `payment_instruments.csv` (1 row per Person) | **fabricated, zero signal**: `instr_bridge_<person_id>`, fixed placeholder type/masked_identifier. Same reasoning as devices. |
| `transactions.csv: transaction_id` (kind in `{purchase, payment_failure}`) | -> | `orders.csv: order_id`, `payments.csv: payment_id` | `ord_bridge_<txn_id>` / `pay_bridge_<txn_id>`, one Order per Payment (1:1), matching the real Heimdall dataset's own convention -- verified independently: 1000/1000 real payments have `order.amount == payment.amount` and a unique order |
| `transactions.csv: from_id` | -> | `orders.csv: customer_id`, `payments.csv: customer_id` | direct (a purchase's `from_id` is always a `person_id`) |
| `transactions.csv: to_id` | -> | `orders.csv: merchant_id`, `payments.csv: merchant_id` | direct (a purchase's `to_id` is always a `merchant_id`) |
| `transactions.csv: amount` | -> | `orders.csv: amount`, `payments.csv: amount` | direct, same value on both (see 1:1 note above) |
| *(none)* | -> | `orders.csv: currency`, `payments.csv: currency` | **fabricated (fixed)**: `"INR"` -- Simulation has no currency field; matches Heimdall's own ingestion default when unset |
| `transactions.csv: kind == "purchase"` | -> | `payments.csv: status = "success"` | direct |
| `transactions.csv: kind == "payment_failure"` | -> | `payments.csv: status = "failed"` | direct |
| `transactions.csv: kind == "payment_failure"` (implied cause: `balance_before < amount`, Simulation's only real failure mechanism) | -> | `payments.csv: failure_reason = "insufficient_funds"` | the one real, causally-verified mapping this bridge makes -- not invented; Simulation produces no other failure cause, so no other `FAILURE_TAXONOMY` category is ever exercised by bridged data |
| `transactions.csv: timestamp` | -> | `orders.csv/payments.csv: created_at`; `payments.csv: authorized_at`, `captured_at` (success only, same value; blank if failed) | direct |
| all other `kind` values (`salary`, `settlement`, `household_sweep`, `savings_sweep`, `org_funding`) | -> | *(skipped entirely)* | not a customer purchase, not a Heimdall Payment on either side of this bridge |
| *(none: `refunds`, `fees`, `settlements`, `settlement_payments`, `bank_transactions`)* | -> | written header-only (0 rows) | Simulation models none of these concepts; written empty so Heimdall's fixed Phase 1 ingestion-step list still runs unmodified end to end |

## What genuinely does not map (the honest gaps)

1. **Device/instrument identity is entirely fabricated.** Simulation has no
   device or payment-instrument model. This bridge invents exactly one
   placeholder of each per Person, purely to satisfy
   `payment_ingestion.py`'s foreign-key requirement. Recovery's decision
   logic never reads either field (verified by reading
   `recovery/signals.py`), so this cannot distort a Recovery result -- but
   it means **Risk cannot be meaningfully bridged this way**: every device
   has exactly one owner, so `risk/runner.py`'s shared-device signal is
   always zero on this data. Building a real Risk bridge would require
   `Simulation/` to grow an actual device/fraud model first -- out of this
   bridge's scope, and out of `Simulation/`'s current scope per its own
   `Rules.md`/`Phases.md`.
2. **Only one of Heimdall's seven failure categories is ever exercised.**
   `FAILURE_TAXONOMY` in `recovery/signals.py` has seven categories
   (`technical_failure`, `timeout`, `insufficient_funds`,
   `authentication_failure`, `issuer_declined`, `risk_block`, `expired`).
   `Simulation/`'s engine only ever produces `payment_failure` via one
   mechanism (insufficient balance) -- there is no simulated network
   timeout, no simulated issuer decline, no simulated fraud block. The real
   end-to-end run below (172 failed payments) therefore produces exactly
   one decision/action pair (`RETRY` / `RETRY_LATER`, score 0.45) for
   every failed payment -- a real, correct result given the input, not a
   bug, but a ceiling on how much of Recovery's logic this bridge can ever
   exercise until `Simulation/` grows more failure mechanisms.
3. **`has_alternate_success` / `has_prior_failed_attempts` are structurally
   always False** on bridged data, same as on the real Heimdall dataset
   (both are 1:1 order:payment corpora) -- this is not a bridge limitation,
   it is the same "built but unexercised" situation `recovery/runner.py`'s
   own comment already documents for the real dataset.
4. **A real, reproducible bug found in existing (frozen, unmodified) code
   while building this bridge**: `financial_state/builder.py`'s
   `build_financial_state(db_path, raw_dir)` correctly *ingests* from the
   given `raw_dir` (its ingestion calls thread `raw_dir` through
   correctly -- confirmed: this bridge's own Payment/Order/Customer counts
   in the built store exactly match this bridge's own generated CSVs). Its
   internal **invariant self-check**, however
   (`_raw_row_count`/`_raw_money_checksum`, builder.py lines ~63-74), reads
   from the module-level `RAW_DIR` constant
   (`financial_system/data/raw/`) instead of the `raw_dir` parameter that
   was actually passed in. Run against this bridge's data, that self-check
   reports spurious `row_count_failures`/`checksum_failures` (e.g.
   "payments.csv: read 9043 rows but CSV has 1000") -- it is comparing this
   bridge's row/checksum counts against the *original, real* dataset's raw
   files, not against the `raw_dir` that was actually ingested. Verified
   independently below: summing `bridge_output/raw/payments.csv`'s `amount`
   column by hand gives `2832406.36`, exactly matching the store's
   "stored sum" -- proving ingestion itself is correct and the failure is in
   the self-check's hardcoded path, not in this bridge or in Phase 1's real
   ingestion logic. **Not fixed** -- `financial_state/builder.py` is an
   existing, frozen file this task must not touch. Reported here because
   the task's own instructions require reporting a real gap precisely
   rather than papering over it, and because a reviewer re-running
   `run_bridge.py` will see this exact `Phase 1 passed=False` output and
   should know why.

## Real end-to-end run (verbatim numbers)

Simulation run: `python run_simulation.py --seed 42 --population 300 --banks 4 --merchants 20 --days 90 --outdir output/bridge_run`
(13,520 transactions, 300 persons, 20 merchants, 90 simulated days).

Bridge run: `python -m financial_system.bridges.run_bridge Simulation/output/bridge_run financial_system/bridges/bridge_output`

```
[1/5] transforming Simulation/ output -> Heimdall raw schema
      persons=300 merchants=20 transactions=13520
      -> orders=9043 payments=9043 customers=300 merchants=20 devices(placeholder)=300 instruments(placeholder)=300
      skipped non-purchase transaction kinds: {'org_funding': 6, 'salary': 900, 'savings_sweep': 900, 'household_sweep': 900, 'settlement': 1771}

[2/5] financial_state.builder.build_financial_state() -- Heimdall's real, unmodified Phase 1
      Phase 1 passed=False row_count_failures=11 checksum_failures=5
      (see "honest gaps" #4 above -- ingestion itself is correct; the self-check compares
      against the wrong, hardcoded directory)

[3/5] entity_resolution.given_matches -- Heimdall's real, unmodified Phase 2 (given-matches only)
      reference-key violations: 0
      given matches persisted: 36172 {'belongs_to': 9043, 'initiated_by': 9043, 'used_device': 9043, 'used_instrument': 9043}

[4/5] financial_graph.builder.build_graph() -- Heimdall's real, unmodified Phase 3
      node counts: {'Customer': 300, 'Device': 300, 'Merchant': 20, 'Order': 9043, 'Payment': 9043, 'PaymentInstrument': 300}
      edge counts: {'belongs_to': 9043, 'initiated': 9043, 'used_device': 9043, 'used_instrument': 9043, 'uses': 600}

[5/5] recovery.recovery_agent.run_recovery_for_payment() -- Heimdall's real, unmodified Phase 7 agent
      failed payments: 172
      decision distribution: {'RETRY': 172}
      proposed_action distribution: {'RETRY_LATER': 172}

BRIDGE RUN: COMPLETE
```

Every one of the 172 bridged failed payments got `decision_score = 0.45`
(the `insufficient_funds` category's own historical base rate, read
straight out of `FAILURE_TAXONOMY` -- unmodified) and
`has_alternate_success = 0.0` (structural, see gap #3). This is not a
degenerate bridge bug: it is the single, correct decision Heimdall's real
Recovery logic makes given that `Simulation/` only ever produces one
failure category. It is also exactly what should make anyone reading this
honest about what this bridge does and does not prove: it proves real,
working interoperation (unmodified Heimdall code making a real,
correctly-reasoned decision on transformed simulated data, structurally
distinct from Heimdall's own real 39.6%-false-retry-rate, seven-category
result), not a rich exercise of Recovery's full decision surface.

## New files

- `financial_system/bridges/__init__.py`
- `financial_system/bridges/simulation_bridge.py` -- the transform (Simulation output -> Heimdall raw-CSV schema)
- `financial_system/bridges/run_bridge.py` -- orchestrates the transform + calls Heimdall's real Phase 1/2/3/Recovery functions, unmodified
- `financial_system/bridges/test_simulation_bridge.py` -- tests for the transform itself (5 tests, all passing)
- `financial_system/bridges/README.md` -- this file
- `financial_system/bridges/bridge_output/` -- one real generated run's output (raw CSVs + `financial_state.db` + `financial_graph.db`), regenerable by re-running the command above; not required to exist for the bridge code itself to work

No file under `financial_system/` or `Simulation/` was modified.
