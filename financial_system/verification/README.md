# Verification Engine (NORTH_STAR.md Section 24, bounded implementation)

`docs/NORTH_STAR.md` Section 24 ("Build the Verification Engine") asks for
verification to become "independent from intelligence... a universal audit
layer" checking eleven properties, from "was the observation valid" to
"can the decision be replayed." This directory is a narrow, concrete,
ADDITIVE-ONLY slice of that: four of the eleven properties, chosen because
they're the ones this codebase already has enough real, frozen machinery
to check for real, on real decisions -- not a redesign of Risk, Recovery,
or Controller, and not a guess at the other seven properties. No file
under `financial_system/`'s existing (non-`verification/`) code was ever
edited to build this -- `git diff --stat financial_system/` only ever
touches files under `financial_system/verification/` itself (verified,
see the task report for the verbatim output).

**Read-only with respect to decision logic.** This module audits verdicts
Risk/Recovery/Controller already produced; it never feeds anything back
into their decisions. `AgentVerdict.decision_score`/`decision` are read,
never written, by anything in this directory.

## The four checks

### 1. Replay correctness (`replay.py`)

Generalizes `financial_system/financial_state/builder.py`'s own Phase 1
self-check (row-count + money-checksum invariant, checked once, right
after ingestion) into a standalone `compute_store_fingerprint()` that
works against ANY already-built `FinancialStateStore` -- and adds the
piece builder.py's own check doesn't do: building the SAME raw input
directory independently twice and comparing fingerprints byte-for-byte
(row counts, every money column's exact Decimal sum, and a sha256 content
hash over every non-provenance-metadata column of every row in all 11
raw-sourced tables).

Deliberately excluded from the content hash: `prov_ingestion_run_id` and
`prov_ingested_at` -- both are wall-clock/uuid values builder.py generates
fresh on purpose every run (`run_id = f"run_{uuid.uuid4().hex[:12]}"`); a
difference there is by design, not a replay failure. Every other column,
including the other three provenance columns (source_file,
source_record_id, row_number), IS part of the hash.

Real result (real Heimdall dataset, 2 independent rebuilds of
`financial_system/data/raw/`): **IDENTICAL** -- row counts, all 10 money
sums, and the content hash matched exactly across both builds.
Real result (bridged Truman run's transformed raw CSVs, 2 independent
rebuilds): **IDENTICAL** too.

### 2. Temporal integrity (`temporal.py`)

Generalizes the ONE real temporal-pinning mechanism this codebase
actually has: Block 5's Risk fix
(`financial_graph/queries.py::edges_to_as_of`, consumed by
`risk/signals.py::compute_device_risk_signals(..., as_of=...)` via
`risk/risk_agent.py::run_risk_for_device(..., as_of=...)`). Its own
docstring states the property directly: "an edge whose subject doesn't
exist yet at as_of carries no evidence at that decision time."
`risk/temporal_runner.py` already benchmarks Risk under this exact
as-of-scoped code path over the real corpus -- this check audits the
VERDICTS that path produces, walking every id in `evidence` and
`affected_entities`, resolving it to a graph node, and confirming that
node's own timestamp never postdates the decision's `as_of`.

**Honest scope note, stated up front, not discovered after the fact:**
`AgentVerdict` carries no timestamp field at all, so this check cannot
discover a verdict's own decision-time by inspecting the verdict --
the caller must supply `as_of` explicitly (exactly how
`run_risk_for_device`'s own real caller, `temporal_runner.py`, already
works). And only Risk's agent function accepts `as_of` in the first place
-- `run_recovery_for_payment` and `run_controller_for_settlement` take no
such argument (confirmed by reading `recovery/recovery_agent.py` and
`reconciliation/controller.py` directly). Inventing a decision-time
boundary for Recovery or Controller that their own frozen code never
claims to honor would be exactly the kind of manufactured violation the
task instructions for this work forbade -- so this module does not do
that. This check runs for real, meaningfully, against Risk only.

**Real result** (every observed payment on every real shared device, both
data sources -- the FULL corpus, not a sample):

| source | as-of decisions audited | evidence ids checked | Payment-evidence violations | other-evidence-type violations |
|---|---|---|---|---|
| real Heimdall dataset | 143 | 2,340 | **0** | 41 (2 Customer ids: `cust_0256`, `cust_0399`) |
| bridged Truman run | 2,583 | 99,084 | **0** | 0 |

Payment-evidence violations are what `edges_to_as_of()` actually claims to
bound (it filters exclusively on `Payment.created_at`) -- **zero on both
data sources**, the honest clean result the task anticipated for an
already-engineered-correctly property; not manufactured.

The 41 non-Payment violations on the real dataset are a real, separately
diagnosed finding, not folded into a false "the fix is broken" narrative:
concretely, `cust_0256` (account `created_at=2026-08-16T17:40:40`) and
`cust_0399` both have real payments, in `financial_system/data/raw/`,
dated BEFORE their own recorded account-creation timestamp (e.g.
`cust_0256` has 7 payments between 2026-07-11 and 2026-08-15, all earlier
than its own `created_at`). That is a raw-data timestamp inconsistency in
`financial_system/data/raw/customers.csv` -- a payment cannot precede the
account that made it -- not a defect in Risk's own as-of code, which never
reads `Customer.created_at` for its boundary at all. Named here, per this
task's explicit instruction, not fixed: `financial_system/data/` is out of
scope. (The bridged Truman run shows 0 such violations, consistent with
this being specific to the real dataset's own generator, not something
inherent to the check itself.)

### 3. Evidence grounding (`grounding.py`)

The same structural idea as
`financial_graph/queries.py::check_no_fabricated_relationships` ("every
edge's endpoints must be real nodes in this same graph"), applied one
layer up: every `AgentVerdict.evidence` entry and `affected_entities`
entry must resolve to a real node in the same graph the verdict was
produced against.

Real result, all three domains, both data sources:

| source | agent | verdicts | evidence checked | evidence missing | affected checked | affected missing |
|---|---|---|---|---|---|---|
| real dataset | risk | 10 | 187 | 0 | 34 | 0 |
| real dataset | recovery | 160 | 320 | 0 | 160 | 0 |
| real dataset | controller | 610 | 2,956 | 0 | 610 | 0 |
| bridged | risk | 41 | 2,712 | 0 | 88 | 0 |
| bridged | recovery | 171 | 342 | 0 | 171 | 0 |
| bridged | controller | 1,770 | 12,354 | 0 | 1,770 | 0 |

Zero dangling ids anywhere, on either data source -- the honest clean
result.

### 4. Idempotency (`idempotency.py`)

Bounded exactly as scoped: calling the SAME domain-agent function on the
SAME subject_id against the SAME graph object twice must produce
byte-identical `AgentVerdict` output, compared field-by-field via
pydantic's `.model_dump()` (not just decision/score/reason -- a silent
drift in `evidence` order or `metrics` would matter too). This is
decision-idempotency, not action-execution-idempotency -- the latter is
`financial_system/action/`'s own already-built exactly-once discipline
(see `financial_state/store.py`'s `apply_payment_retry_success`
docstring), a different piece of the codebase, out of scope here.

Real result, one real subject per domain, both data sources: **all six
identical** across two calls each.

## Honest caveats -- what this does NOT check

This implements 4 of NORTH_STAR §24's 11 named properties. Explicitly
NOT built here (bounded scope, not an oversight):

- **Was the observation valid? Was the state correct?** -- no independent
  re-derivation of Financial State from an external source of truth;
  check #1 only proves the ingestion pipeline is a pure, reproducible
  function of its raw input, not that the raw input itself is correct.
- **Was the policy satisfied? Was the economic calculation correct? Was
  the action authorized?** -- would require auditing `financial_system/
  policy/` and `financial_system/action/`'s own EV/authorization logic,
  explicitly out of this task's scope (Risk/Recovery/Controller/graph/
  state only).
- **Did the outcome occur? Was the world updated correctly?** -- would
  require correlating a decision against `financial_system/events/`'s
  event log post-execution; not attempted here.
- Temporal integrity (#2) is only meaningfully exercised for Risk, the
  only domain with a real as-of mechanism today -- see the honest scope
  note above. Generalizing an as-of concept INTO Recovery/Controller
  would be a change to their decision logic, which this task's hard
  boundary forbids.
- The 41 Customer-timestamp violations found by check #2 on the real
  dataset are reported, not resolved -- `financial_system/data/` is
  out-of-bounds for this task.
- Graph node timestamps only exist for 5 of 10 node types (`Customer`,
  `Device`, `Payment`, `Settlement`, `BankTransaction`) --
  `financial_graph/builder.py`'s `_build_nodes()` never copies
  `Merchant`/`Order`/`Refund`/`Fee`/`PaymentInstrument`'s own `created_at`
  (present in the underlying `FinancialStateStore` row) into graph node
  properties. Evidence ids of those types are counted separately
  (`skipped_no_timestamp`) by check #2, never silently treated as
  "verified clean."

## Files

- `financial_system/verification/__init__.py`
- `financial_system/verification/replay.py` -- check 1
- `financial_system/verification/temporal.py` -- check 2
- `financial_system/verification/grounding.py` -- check 3
- `financial_system/verification/idempotency.py` -- check 4
- `financial_system/verification/report.py` -- plain Markdown report builder (same convention as `Simulation/validation/report.py`)
- `financial_system/verification/run_verification.py` -- runs all 4 checks against the real dataset AND a bridged Truman run, prints the report. Run directly: `python -m financial_system.verification.run_verification [work_dir] [sim_outdir]`
- `financial_system/verification/verification_test.py` -- test suite (8 tests: a real-data pass + a named synthetic-fixture positive-detection case for each of the 4 checks). Run directly: `python -m financial_system.verification.verification_test`
- `financial_system/verification/README.md` -- this file

All db files a run of `run_verification.py` or `verification_test.py`
produces (replay-correctness rebuilds, the bridge's own state/graph dbs)
go to a disposable system-temp directory by default -- nothing under
`financial_system/data/` or `financial_system/bridges/bridge_output/` is
touched beyond what running `risk/runner.py`, `recovery/runner.py`, or
`reconciliation/runner.py` themselves already do (rebuilding
`financial_graph.db` in place via `financial_graph.builder.build_graph()`
is exactly what those runners do too).
