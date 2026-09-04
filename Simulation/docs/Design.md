# Design — Financial World Simulation

This project has no user interface in Phase 1 — it's a backend
simulation producing data files. The usual meaning of "Design.md"
(colors, theme, typography) doesn't apply, so this file covers the
equivalent decisions for a data-generating system: how output is
shaped and named, so it stays consistent and readable as the project
grows.

## Output format

CSV for tabular event/transaction logs, matching
`financial_system/data/raw/`'s own convention (plain, inspectable,
diffable, no binary formats). JSON only where a record's shape is
genuinely nested (e.g. a payload with variable fields) and a flat CSV
would lose information.

## Naming conventions

- IDs: `<type_prefix>_<short_id>`, e.g. `person_0001`, `bank_01`,
  `txn_<uuid8>` — human-scannable, not raw UUIDs, matching
  `financial_system`'s own `pay_...`/`cust_...` style.
- Files: lowercase, underscore-separated, one file per entity/event
  type (`persons.csv`, `transactions.csv`, `events.csv`), not one
  giant combined file.
- Timestamps: ISO 8601, UTC, matching the rest of this repo.
- `Transaction.kind` vocabulary (as of the live-recovery-loop task,
  `docs/Memory.md`'s entry for it): `salary | purchase | payment_failure |
  settlement | savings_sweep | household_sweep | org_funding |
  retry_success | retry_failure`. The last two are new — emitted only by
  `world/engine.py`'s `SimulationEngine.attempt_retry()`, an additive,
  opt-in method never called from `run()`/`_run_one_day()` (so they never
  appear in a normal `run_simulation.py` invocation's output). A retry
  transaction's link back to the original failed transaction it retries is
  carried in the corresponding `Event.payload` JSON's `retried_from` key,
  not as a new `Transaction` field — see `attempt_retry()`'s own docstring
  for why (a new always-present dataclass field would add a column to
  every `transactions.csv` row on every run, breaking that task's own
  byte-identical-default-output requirement; `payload` is already this
  project's stated convention for "JSON only where a record's shape is
  genuinely nested," per this section's original text above).
- **Device-blocked purchase failures (as of the live-risk-loop task,
  `docs/Memory.md`'s entry for it) reuse `kind="payment_failure"` — no
  new `kind` value.** Unlike a retry (a structurally different kind of
  event), a device-blocked purchase attempt is still honestly "an
  attempted purchase that failed," just with a different cause —
  Heimdall's own real `FAILURE_TAXONOMY` already names a `risk_block`
  category for exactly this situation. The distinct cause is carried at
  the `Event` layer instead: a new `event_type` value
  (`purchase_blocked_device`, never `purchase_failed`) and a
  `blocked_device: true` key in the `Event.payload` JSON, added to
  `_record()`'s existing optional-key mechanism the same way
  `retried_from` was (above) — emitted only via
  `SimulationEngine.block_device()`'s effect on
  `_maybe_attempt_purchase()`, an additive, opt-in method never called
  from `run()`/`_run_one_day()` (so it never appears in a normal
  `run_simulation.py` invocation's output).

## Statistics/report output

`stats/report.py`'s output should be plain text or Markdown, printed
to console and optionally saved to a file — no dashboard, no charts,
until there's an actual audience that needs one. A table of numbers
(transaction volume, failure rate, distribution summary) is enough
for Phase 1's purpose: proving the mechanism works, not presenting it.

## Code style

Match the conventions already established in `financial_system/`:
plain, well-commented Python, dataclasses or Pydantic models for
typed records (whichever this project ends up using — pick one and
stay consistent), no unnecessary abstraction layers for a Phase-1
prototype.
