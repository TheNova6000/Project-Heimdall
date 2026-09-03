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
