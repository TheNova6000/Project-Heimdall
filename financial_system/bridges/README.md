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

## Why Recovery, not Risk or Controller (ORIGINAL bridge; Risk added later -- see below)

Three domains were possible; only one was actually buildable against what
`Simulation/` produced AT THE TIME this bridge was first built:

- **Risk** (`financial_system/risk/`) needs shared-device fraud-ring
  structure: `risk/runner.py`'s `devices_with_sharers()` only ever produces
  a nonzero score for a Device node with >=2 distinct Customers. `Simulation/`
  had no Device, PaymentInstrument, or fraud concept at all --
  `Simulation/output/*/persons.csv` had no such columns, and nothing in
  `Simulation/world/` modeled shared devices. A bridge could only ever
  produce one placeholder Device per Person (see "Fabricated fields"
  below), which made Risk's whole signal structurally vacuous -- not a
  real test of Risk, just zeros. **This has since changed** -- see
  "Part 2: Risk, now that Device is real" below, a later, explicit,
  user-requested follow-on task that gave `Simulation/` a real `Device`
  entity and extended this bridge to use it. Controller remains unbuilt,
  for the reason below.
- **Controller** (settlement reconciliation) needs Settlement and
  BankTransaction records with fee/tax breakdowns matched against bank
  deposits. `Simulation/` has a `settlement` transaction kind (merchant ->
  bank), but it is a single merchant-owned balance movement, not
  Razorpay-shaped per-payment settlement batching with fees -- mapping it
  onto Controller's schema would mean inventing a settlement-batching
  policy Simulation never actually decided, not transforming real signal.
  Still unbuilt; still out of scope.
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

Recovery was the only domain where the bridge was a real transform of real
signal, not a structural formality producing meaningless output, at the
time it was first built. It is unchanged by the later Risk work below.

## Part 2: Risk, now that Device is real (later, user-requested follow-on)

`Simulation/` grew a real `Device` entity (`Simulation/world/models.py`,
`Simulation/world/engine.py` -- see `Simulation/docs/Memory.md`'s "Device"
section for the full design). Every Person now maps to exactly one real
Device; the one legitimate sharing mechanism modeled is a household's
members optionally sharing the household's "primary" device
(`DEVICE_HOUSEHOLD_SHARING_FRACTION = 0.3`, a named MODELING ASSUMPTION --
see `Simulation/docs/Memory.md` for its full provenance/justification). No
fraud-ring mechanism was added anywhere -- `Simulation/` still does not
model fraud, by explicit, repeated design choice (`Simulation/docs/
Research.md` Part C.1).

This bridge (`simulation_bridge.py`) now reads `Simulation/`'s real
`devices.csv` and each transaction's own real `device_id` column directly,
instead of fabricating one placeholder Device per Person. `run_bridge.py`
now also calls Heimdall's real, unmodified `risk/runner.py` /
`risk/risk_agent.py` logic (`devices_with_sharers()` +
`run_risk_for_device()`) on every bridged Device with >=2 distinct owning
Customers -- exactly Risk's own real definition of "has any signal to
score at all."

**The honest result** (see "Real end-to-end run" below for verbatim
numbers): Risk's real scoring logic runs meaningfully on bridged data for
the first time -- it finds real Devices shared by >=2 real Customers,
computes real burst/account-age signals over their real payment history,
and produces real MEDIUM-tier ("REVIEW") verdicts for some of them. It
produces **zero HIGH-tier ("HOLD") verdicts** -- because `Simulation/`
genuinely does not simulate the burst-of-payments-from-a-newly-created-
account pattern that drives a HIGH score (`risk/signals.py`'s
`max_burst_count`/`min_account_age_days` signals), only honest, steady-
state household device sharing. This is the CORRECT and expected result
given honest input, per this task's own framing -- not a gap to fix. Risk's
decision/scoring logic itself was not touched, examined for tuning, or
adjusted in any way to produce a more "interesting" result.

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
| `devices.csv: device_id`, `fingerprint` | -> | `devices.csv: device_id`, `fingerprint` | **REAL, direct** (later addition -- see "Part 2" above): one row per real Simulation `Device`, including genuine multi-owner (household-shared) devices. `devices.csv: first_seen_at` is still fabricated (earliest observed transaction on that device, or the run's overall earliest timestamp if the device never appears in one) -- Simulation's `Device` has no creation-date field of its own. |
| `transactions.csv: device_id` (kind in `{purchase, payment_failure}`) | -> | `payments.csv: device_id` | **REAL, direct** (later addition): the payer's own real device, or their household's shared device if that's who transacted -- exactly what Simulation recorded. |
| *(none)* | -> | `payment_instruments.csv` (1 row per Person, keyed off the person's real `device_id`) | **fabricated, zero signal** (unchanged fabrication, updated shape): `instr_<device_id>_<person_id>`, fixed placeholder type/masked_identifier. Simulation still has no payment-instrument concept distinct from a device. Neither `recovery/signals.py` nor `risk/signals.py` reads this field's content (confirmed by reading both), so it cannot distort either decision. |
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

1. **~~Device/instrument identity is entirely fabricated~~ -- RESOLVED for
   Device, still true for PaymentInstrument.** (Original gap, now
   partially closed by the later Device follow-on task -- kept here,
   struck through, rather than silently deleted, so the history is
   honest.) Device identity is now real: `Simulation/` grew a real
   `Device` entity with a real, tested household-sharing mechanism (see
   "Part 2" above), and this bridge now reads it directly instead of
   fabricating a placeholder. `PaymentInstrument` is still entirely
   fabricated -- `Simulation/` still has no payment-instrument concept
   distinct from a device -- but neither Recovery's nor Risk's decision
   logic reads its content (confirmed by reading both `recovery/
   signals.py` and `risk/signals.py`), so this remaining fabrication
   cannot distort either domain's result.
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
4. **~~A real, reproducible bug found in existing (frozen, unmodified)
   code~~ -- FIXED in a separate, later session** (kept here, historical,
   rather than deleted, for an honest record). `financial_state/
   builder.py`'s invariant self-check (`_raw_row_count`/
   `_raw_money_checksum`) previously read from the module-level `RAW_DIR`
   constant instead of the `raw_dir` parameter actually passed in,
   producing spurious `row_count_failures`/`checksum_failures` on any
   non-default `raw_dir` (including this bridge's). That bug was found,
   confirmed precisely, fixed, and verified against `financial_system`'s
   frozen Risk (100.0%/96.3%/0.0%) and Recovery (87/87, 39.6%) baselines
   in a separate session (commit `b939387`, "Fix Phase 1 invariant
   self-check to use the actual raw_dir it was called with") -- not part
   of this Device/Risk-bridge task, and not re-touched here. Its practical
   effect on this bridge: `Phase 1 passed=True` now, cleanly, on bridged
   data (see the real run below) instead of the spurious `False` this
   README previously reported.

## Real end-to-end run (verbatim numbers)

**Simulation run**: `python run_simulation.py --seed 42 --population 300 --banks 4 --merchants 20 --days 90 --outdir output/bridge_run_device`
(13,556 transactions, 300 persons, 20 merchants, 90 simulated days, 253 real Devices).

**Bridge run**: `python -m financial_system.bridges.run_bridge Simulation/output/bridge_run_device financial_system/bridges/bridge_output`

```
[1/6] transforming Simulation/ output (Simulation\output\bridge_run_device) -> Heimdall raw schema (financial_system\bridges\bridge_output\raw)
      persons=300 merchants=20 transactions=13556 devices=253
      -> orders=9080 payments=9080 customers=300 merchants=20 devices(real)=253 (of which shared by >=2 owners: 41) instruments(fabricated 1:1-per-device wrapper)=300
      skipped non-purchase transaction kinds: {'org_funding': 6, 'salary': 900, 'savings_sweep': 900, 'household_sweep': 900, 'settlement': 1770}

[2/6] financial_state.builder.build_financial_state() -- Heimdall's real, unmodified Phase 1
      Phase 1 passed=True row_count_failures=0 checksum_failures=0

[3/6] entity_resolution.given_matches -- Heimdall's real, unmodified Phase 2 (given-matches only)
      reference-key violations: 0
      given matches persisted: 36320 {'belongs_to': 9080, 'initiated_by': 9080, 'used_device': 9080, 'used_instrument': 9080}

[4/6] financial_graph.builder.build_graph() -- Heimdall's real, unmodified Phase 3
      node counts: {'Customer': 300, 'Device': 253, 'Merchant': 20, 'Order': 9080, 'Payment': 9080, 'PaymentInstrument': 300}
      edge counts: {'belongs_to': 9080, 'initiated': 9080, 'used_device': 9080, 'used_instrument': 9080, 'uses': 600}

[5/6] recovery.recovery_agent.run_recovery_for_payment() -- Heimdall's real, unmodified Phase 7 agent, called on every bridged failed Payment
      failed payments: 171
      decision distribution: {'RETRY': 171}
      proposed_action distribution: {'RETRY_LATER': 171}

[6/6] risk.runner.devices_with_sharers() + risk.risk_agent.run_risk_for_device() -- Heimdall's real, unmodified Phase 6 agent, called on every bridged Device with >=2 owners
      devices with >=2 distinct owning customers: 41
      decision distribution: {'RELEASE': 35, 'REVIEW': 6}
      decision_score range: 0.095 .. 0.550

BRIDGE RUN: COMPLETE
```

**Recovery (unchanged behavior from the original bridge, confirmed not
regressed)**: every one of the 171 bridged failed payments got
`decision_score = 0.45` (the `insufficient_funds` category's own
historical base rate, read straight out of `FAILURE_TAXONOMY` --
unmodified) and `has_alternate_success = 0.0` (structural, see gap #3).
This is not a degenerate bridge bug: it is the single, correct decision
Heimdall's real Recovery logic makes given that `Simulation/` only ever
produces one failure category. (The count differs slightly from the
original bridge session's 172 -- 171 here -- purely because this is a
freshly regenerated Simulation run under the Device follow-on task's own
engine changes, which add new RNG draws for device assignment; still the
same seed=42/300-person/90-day parameters, still fully deterministic
given that seed, not a sign of any regression -- see the Simulation-side
determinism checks in the main task report.)

**Risk (new, real result)**: of 41 real Devices shared by >=2 distinct
Customers, Risk's real, unmodified scoring logic decided `RELEASE` for 35
and `REVIEW` for 6 (`decision_score` range 0.095-0.550) -- **zero `HOLD`
verdicts** (Risk's HIGH tier requires `decision_score >= 0.6`; the highest
score observed here, 0.550, sits in MEDIUM). This is the honest,
CORRECT result for genuinely-benign, non-fraud shared-device structure:
`Simulation/` models real household device sharing (steady-state, ongoing
use by cohabiting people) but no fraud-ring pattern at all (no burst of
payments from a newly-created account, the actual signal that would drive
a HIGH score in `risk/signals.py`) -- so Risk correctly finds nothing to
escalate. This is not a null result to fix; it is exactly what proving
"the plumbing is real" was supposed to look like on data that was never
designed to contain fraud.

Both runs together demonstrate real, working interoperation on BOTH
domains now: unmodified Heimdall code making real, correctly-reasoned
decisions on transformed simulated data -- structurally distinct from
Heimdall's own real 39.6%-false-retry-rate/seven-category Recovery
result and its own real 100.0%/96.3%/0.0% Risk result against actual
fraud-ring ground truth, since neither seven failure categories nor any
fraud ring exists in `Simulation/`'s data by design -- not a rich
exercise of either domain's full decision surface, and not claimed to be.

## New files

- `financial_system/bridges/__init__.py`
- `financial_system/bridges/simulation_bridge.py` -- the transform (Simulation output -> Heimdall raw-CSV schema; now includes real Device data, see "Part 2" above)
- `financial_system/bridges/run_bridge.py` -- orchestrates the transform + calls Heimdall's real Phase 1/2/3/Recovery/Risk functions, unmodified
- `financial_system/bridges/test_simulation_bridge.py` -- tests for the transform itself (6 tests, all passing)
- `financial_system/bridges/README.md` -- this file
- `financial_system/bridges/bridge_output/` -- one real generated run's output (raw CSVs + `financial_state.db` + `financial_graph.db`), regenerable by re-running the command above; not required to exist for the bridge code itself to work

No file under `financial_system/`'s existing (non-`bridges/`) code, and no
file under `Simulation/`'s existing engine/world code other than the
explicitly-scoped Device addition (see the main task report / `Simulation/
docs/Memory.md`'s "Device" section), was modified.
