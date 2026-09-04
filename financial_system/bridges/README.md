# Simulation -> Heimdall bridge (Working Section 23, bounded implementation)

`docs/SIMULATION_ARCHITECTURE_SPEC.md`'s Working Section 23 describes a full
observation-boundary/action-writeback bridge and explicitly does not build
it ("naming what the eventual bridge would need to look like... without
building any of it"). This directory is a narrower, concrete, ADDITIVE-ONLY
slice of that: a real, running one-way bridge that transforms a completed
`Simulation/` run's output into `financial_system/`'s real raw-CSV input
schema, and calls Heimdall's actual, unmodified Phase 1/2/3/Recovery/Risk/
Controller functions on it -- all three decision domains, as of the
Controller follow-on task below. No file under `financial_system/`'s
existing (non-`bridges/`) code was ever edited to build any of this --
`git diff --stat financial_system/` only ever touches files under
`financial_system/bridges/` itself.

**No writeback.** This bridge only reads a finished `Simulation/` run and
produces Heimdall decisions; it does not write an Action back into a
running `Simulation/` world (Working Section 23's item (2)/(3) --
`Simulation/` only ever produces a finished CSV export, has no paused/live
world to act into, and has no retry mechanism yet). That remains exactly as
unbuilt as the spec says.

## Domain bridge registry (2026-09-04, later follow-on task)

The three bridges below (Recovery, Risk, Controller) were each built as
one-off, separately-coded transform logic, with no catalog tracking what
was bridged, what wasn't, or why. This later task formalizes that into a
real, documented, extensible **domain registry** --
`financial_system/bridges/registry.py` -- implementing
`docs/NORTH_STAR.md` §26 ("Domain Package Architecture") and §28
("Capability Graph") concretely, at a bounded, honest scale. It wraps and
catalogs the exact same transform/agent functions described in the rest
of this file -- it does not reimplement or alter one byte of their logic
(`simulation_bridge.py` and `run_bridge.py` are byte-for-byte unmodified
by this task; see "Verification" below).

**What this is: a structured catalog.** Registering a domain means
constructing one `DomainBridge` dataclass and calling `register_domain()`
-- a well-defined, discoverable, testable process. `capability_report.py`
reads the registry and prints it in a "Capability Graph" style.

**What this is NOT: machine learning, autonomy, or self-modifying code.**
Nothing in `registry.py` scans code, infers a new domain's fields from
data, or decides on its own that a domain should move from `BLOCKED` to
`BRIDGED`. A human/agent reads the real, frozen code and calls
`register_domain()` explicitly, every time. This is stated plainly in
`registry.py`'s own module docstring, and repeated here so it is never
mistaken for more than it is.

### The `DomainBridge` structure

```python
@dataclass(frozen=True)
class DomainBridge:
    domain_name: str
    status: Literal["BRIDGED", "BLOCKED"]
    heimdall_entry_point: str          # the real callable (BRIDGED) or "does not exist yet" (BLOCKED)
    required_truman_fields: list[str]  # extracted from real code, never invented
    transform_fn: Callable | None      # BRIDGED only -- the real transform
    blocked_reason: str | None         # BLOCKED only -- reused verbatim from this file / Research.md Part C
    last_verified: str                 # a real commit hash + pointer, never a bare timestamp
```

A `__post_init__` check refuses to construct a `BRIDGED` entry with no
`transform_fn`, or a `BLOCKED` entry with no `blocked_reason` -- the
registry cannot represent a half-stated claim.

### The six real domains

| domain | status | heimdall_entry_point | required_truman_fields (summary) |
|---|---|---|---|
| `recovery` | BRIDGED | `recovery.recovery_agent.run_recovery_for_payment()` | `transactions.csv: kind` -> `payments.csv: status`/`failure_reason='insufficient_funds'`; 1:1 order:payment for the sibling-success check |
| `risk` | BRIDGED | `risk.runner.devices_with_sharers()` + `risk.risk_agent.run_risk_for_device()` | `devices.csv` (real, direct); `transactions.csv: device_id` -> `payments.csv: device_id` |
| `controller` | BRIDGED | `reconciliation.controller.run_controller_for_settlement()` | `transactions.csv: kind=='settlement'` -> `settlements.csv`/`bank_transactions.csv`; T+1 purchase grouping -> `settlement_payments.csv` |
| `fraud` | BLOCKED | does not exist yet | `Person.fraud_propensity`, `Transaction.kind` values (`fraud_attempt`, ...), `Transaction.is_fraudulent`, behavioral `Merchant.category` multiplier -- none exist |
| `credit` | BLOCKED | does not exist yet | `Person.credit_score` (300-850), a `CreditEvent` -- neither exists |
| `loan` | BLOCKED | does not exist yet | a `Loan` dataclass, a `Bank` loans registry -- neither exists |

Full field lists and exact `blocked_reason` text (reused verbatim from
this file's own gap sections above and `Simulation/docs/Research.md` Part
C, not rephrased) are in `registry.py` itself.

### A seventh, demonstration-only entry: `coverage`

To prove the registry is a real extension point and not just a static
list (see `financial_system/bridges/coverage_check.py`), a fourth,
genuinely new "domain" is registered through the exact same mechanism,
from a separate module (`capability_report.py`) that only imports
`registry.py`'s public API -- proving a caller outside the registry's own
module can extend it. `coverage` is a basic, count-based reconciliation
summary (of all bridged successful purchases, what fraction were swept
into a settlement?) chosen specifically because it needs **zero** new
Simulation/ or Heimdall work: `payments.csv` and `settlement_payments.csv`
are already written by the existing transform for Recovery/Controller's
own use. It is explicitly marked `BRIDGED` with
`heimdall_entry_point="none"` -- it produces no `AgentVerdict` and is not
a claim that a fourth real Heimdall decision domain exists; it is a
registry-mechanism demonstration only.

### How to add domain N+1

1. Read the real, frozen code the new domain would consume (a Heimdall
   agent's `signals.py`, if it exists) and/or the design doc naming what's
   missing (e.g. another `Simulation/docs/Research.md` Part C entry).
2. Write a small, real transform function (or, if genuinely blocked, skip
   this step) -- pure, reading only already-available input, writing only
   to a caller-supplied path, same discipline as `simulation_bridge.py`'s
   own module docstring states.
3. Construct one `DomainBridge(...)`: `domain_name`, `status`,
   `heimdall_entry_point` (the real callable, or "does not exist yet"),
   `required_truman_fields` (extracted from the real transform/design doc,
   never invented), `transform_fn` xor `blocked_reason`, and a real
   `last_verified` (a commit hash, optionally with a pointer to the
   specific run/test that verified it).
4. Call `register_domain(entry)` -- from any module that imports
   `financial_system.bridges.registry`, exactly like
   `capability_report.py` does for `coverage` above.
5. Run `python -m financial_system.bridges.capability_report <sim_outdir>
   [bridge_outdir]` and confirm the new entry appears with real output.
6. Add a test asserting the new entry's presence/status/fields, following
   `test_registry.py`'s pattern.

### Real capability report output (verbatim, one real run)

```
=== Heimdall Domain Bridge Registry -- Capability Report ===
(A structured catalog, not an autonomous or self-learning system --
 see financial_system/bridges/registry.py's module docstring.)

BRIDGED (4)
-----------
recovery  -- BRIDGED
  Heimdall entry point: financial_system.recovery.recovery_agent.run_recovery_for_payment(graph, payment_id, investigate=False) -- Heimdall's real, unmodified Phase 7 agent
  Live run summary: 171 failed payments; decision distribution {'RETRY': 171}; proposed_action distribution {'RETRY_LATER': 171}

risk  -- BRIDGED
  Heimdall entry point: financial_system.risk.runner.devices_with_sharers(graph) to select candidate Devices, then financial_system.risk.risk_agent.run_risk_for_device(graph, device_id, investigate=False) -- Heimdall's real, unmodified Phase 6 agent
  Live run summary: 41 devices with >=2 owners scored; decision distribution {'RELEASE': 35, 'REVIEW': 6}; decision_score range 0.095..0.550

controller  -- BRIDGED
  Heimdall entry point: financial_system.reconciliation.controller.run_controller_for_settlement(graph, settlement_id, investigate=False) -- Heimdall's real, unmodified Phase 5 agent, whose core arithmetic lives in reconciliation.deterministic.reconcile_settlement()
  Live run summary: 1770 settlements; decision distribution {'PASS': 1770}

coverage  -- BRIDGED
  Heimdall entry point: none -- this is a bridge-side deterministic check, not a Heimdall agent decision. Registered specifically to demonstrate the registry's extension mechanism, not to claim a fourth real Heimdall decision domain exists.
  Live run summary: 8909 successful payments; 8814 covered by a settlement (98.9%)

BLOCKED (3)
----------
fraud  -- BLOCKED (Simulation/ does not model fraud at all, by explicit, repeated design choice; see Research.md Part C.1)
credit  -- BLOCKED (credit_score needs new PERSISTENT agent state outside Phase 2's ledger-invariant discipline; see Research.md Part C.2)
loan  -- BLOCKED (Loan needs a new persistent liability-side object Phase 2 never designed for; see Research.md Part C.3)
```

(Full text, including every `required_truman_fields` line and full
`blocked_reason` text, is produced by
`python -m financial_system.bridges.capability_report <sim_outdir>`;
truncated here for length -- see `test_registry.py` for the
machine-checked version of these same claims.)

### Verification (registry task, no behavior change)

Before AND after this task's changes, `run_bridge.py` (unmodified) was run
on the same fresh `Simulation/` run (seed=42, population=300, banks=4,
merchants=20, days=90). Every one of the three domains' real decision
distributions was byte-for-byte identical, and the two runs' raw output
directories diffed empty:

```
recovery:   171 failed payments, decision distribution {'RETRY': 171}, proposed_action {'RETRY_LATER': 171}
risk:       41 devices scored, decision distribution {'RELEASE': 35, 'REVIEW': 6}, score range 0.095..0.550
controller: 1770 settlements, decision distribution {'PASS': 1770}
```

`financial_system.risk.runner` and `financial_system.recovery.runner`
(against the real, unmodified dataset) were also re-run and confirmed
unaffected: Risk precision=100.0% recall=96.3% false-positive-rate=0.0%
(tp=26 fp=0 tn=373 fn=1); Recovery category accuracy=100.0%, recovery rate
87/87 (100.0%), false-retry rate 57/144 (39.6%). `git diff --stat
financial_system/` for this task touches only new files under
`financial_system/bridges/` (`registry.py`, `coverage_check.py`,
`capability_report.py`, `test_registry.py`) -- `simulation_bridge.py` and
`run_bridge.py` are byte-for-byte unmodified.

### New files (this task)

- `financial_system/bridges/registry.py` -- the `DomainBridge`
  dataclass, `register_domain()`/`get_domain()`, and the six real
  Recovery/Risk/Controller/fraud/credit/loan entries
- `financial_system/bridges/coverage_check.py` -- the demonstration
  transform (`compute_settlement_coverage()`)
- `financial_system/bridges/capability_report.py` -- registers the
  `coverage` domain and prints the full capability report; runnable
  directly (see above)
- `financial_system/bridges/test_registry.py` -- registry tests (9
  tests, all passing)

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
  entity and extended this bridge to use it.
- **~~Controller~~ (settlement reconciliation) -- RESOLVED, later
  follow-on task (see "Part 3: Controller" below).** At the time this
  section was first written, `Simulation/`'s `settlement` transaction kind
  looked like "a single merchant-owned balance movement, not
  Razorpay-shaped per-payment settlement batching" -- that judgment turned
  out to be wrong on closer reading of `world/engine.py`'s
  `_run_settlement()`: it already runs once per merchant per simulated
  day, sweeping that merchant's whole pending balance in one batch --
  structurally IDENTICAL to a Heimdall Settlement batch, no
  settlement-batching policy needed to be invented at all. What was
  actually missing was just the transform-layer work of mapping it onto
  Controller's CSV schema and reconstructing which payments each batch
  covered -- done in the later task, kept here struck-through rather than
  silently deleted, same honest-history convention as the Device gap
  below.
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

## Part 3: Controller, now that Simulation's settlement sweep is bridged (later, user-requested follow-on)

`Simulation/`'s engine has ALWAYS had a real settlement mechanism --
`world/engine.py`'s `_run_settlement()`, run once per simulated day before
that day's Person loop, sweeps every Merchant's pending
(received-but-not-yet-settled) balance into their settled account in one
batch transfer per merchant per day, exactly T+1 (confirmed by reading
`_run_settlement`'s own code and docstring directly -- not assumed; see
`Simulation/docs/Memory.md`'s Phase 2 section for the research grounding
of the T+1 choice). This IS, structurally, already a Heimdall Settlement
batch -- one per merchant per day -- so no new `Simulation/` engine
feature was needed to bridge Controller; this was a transform-layer-only
task, same boundary as Recovery and Risk before it. `git diff --stat
Simulation/` is empty for this task.

Controller's real reconciliation logic (confirmed by reading
`reconciliation/deterministic.py`'s `reconcile_settlement()` directly)
needs exactly three things from the graph: a `Settlement` node with a
`net_amount` property; a `deposited_as` edge from that Settlement to one
or more `BankTransaction` nodes (summed for the "actual" side); and
`contains` edges from the Settlement to the `Payment`s it covers (used
only for a duplicate-line-item check). **It never reads `fee_amount` or
`tax_amount` at all**, despite `settlements.csv` having those columns --
confirmed directly by reading the function body, not assumed. This
matters because `Simulation/` has no fee/tax concept whatsoever: this
bridge fabricates `fee_amount = tax_amount = 0` (so `gross_amount ==
net_amount` always), stated plainly as a gap below, but since Controller
never reads either field, this fabrication cannot distort a single
Controller decision -- unlike the Device/PaymentInstrument gap in Part 2,
this one is fully inert by construction, not just "probably fine."

**The `deposited_as` edge is NOT given directly by any raw CSV column** --
confirmed by reading `entity_resolution/bank_settlement_matcher.py` and
`financial_graph/builder.py` directly. It is resolved by Phase 2 step 6's
real matcher: a deterministic description-substring pass first (does a
bank transaction's free-text `description` contain a settlement's own
id-suffix?), falling back to amount+date corroboration only when that
fails. This bridge's `bank_transactions.csv` descriptions are built as
`"RAZORPAY <settlement_id's own last 8 chars> SETTLEMENT BRIDGE"` --
deliberately shaped so the real matcher's deterministic pass resolves
every single bridged settlement's `deposited_as` edge on its own (see
"Real end-to-end run" below: 1770/1770 deterministic, 0 unresolved), the
same mechanism the real dataset's own `bank_transactions.csv` relies on
(`"RAZORPAY <suffix> SETTLEMENT"`). `run_bridge.py` now also calls this
real matcher (`resolve_settlement_bank_matches()`, Phase 2 step 6) before
building the graph -- the original bridge/Part 2 explicitly skipped this
step (bridged data had no settlements/bank_transactions to match at all);
it is invoked for real now that there is real data for it to resolve. Its
ground-truth scoring (Phase 2 steps 7-8, run only inside
`entity_resolution/runner.py`'s `run_phase2()`) is intentionally still
NOT invoked -- it scores against `financial_system/`'s own real answer
key (`ground_truth/entity_resolution_labels.csv`), which has no bearing
on bridged settlement ids.

**The `contains` edge** (Settlement -> Payment, used for the
duplicate-line-item check) comes from the opposite side: Phase 2's given
matches (`entity_resolution/given_matches.py`, steps 2-5) turn every
`settlement_payments.csv` row into a `settles_into` (Payment ->
Settlement) `EntityMatch`, and `financial_graph/builder.py` adds the
`contains` inverse automatically for every `settles_into` edge. This
bridge's `settlement_payments.csv` rows are the one piece of real
structural work in this task (see "Payment-grouping verification" below)
-- everything else here is closing the plumbing between existing real
mechanisms.

### Field mapping (Controller-specific; extends the table below)

| Simulation field | -> | Heimdall field | Notes |
|---|---|---|---|
| `transactions.csv: kind == "settlement"` (one per merchant per simulated day, T+1 sweep) | -> | `settlements.csv: settlement_id`, `bank_transactions.csv: bank_txn_id` | `settle_bridge_<txn_id>` / `bank_bridge_<txn_id>`, one Settlement + one BankTransaction per settlement transaction -- direct, real structural mapping, not invented |
| `transactions.csv: to_id` (settlement's merchant) | -> | `settlements.csv: merchant_id` | direct |
| `transactions.csv: timestamp` (settlement's own date) | -> | `settlements.csv: settlement_date`, `bank_transactions.csv: value_date` | direct, same value on both -- Simulation has no simulated bank-clearing delay, so "when the bank recorded it" is honestly identical to "when the settlement was recorded" |
| `transactions.csv: amount` (the pending balance swept) | -> | `settlements.csv: gross_amount`, `net_amount`, `bank_transactions.csv: amount` | direct, same value on all three -- Simulation has no fee concept, so gross == net, and no banking discrepancy, so the "actual" bank deposit is honestly identical to the settlement's own recorded amount |
| *(none)* | -> | `settlements.csv: fee_amount`, `tax_amount` | **fabricated (fixed `0`)** -- Simulation has no fee/tax concept at all. **Controller's `reconcile_settlement()` never reads either field** (confirmed by reading `reconciliation/deterministic.py` directly), so this fabrication is fully inert, not just low-impact |
| *(none)* | -> | `bank_transactions.csv: utr`, `description` | **fabricated**: deterministic placeholders (`UTRBRIDGE<hex>`, `"RAZORPAY <suffix> SETTLEMENT BRIDGE"`) -- Simulation has no UTR/bank-statement-description concept. `description` is shaped specifically to carry the settlement_id's own suffix so Phase 2 step 6's real deterministic-description matcher resolves the `deposited_as` edge (see above) |
| that merchant's successful `purchase` transactions from the calendar day immediately before the settlement's own date (T+1, `_run_settlement`'s own timing) | -> | `settlement_payments.csv: (settlement_id, payment_id)` pairs | **REAL, direct, reconstructed** -- the one real structural transform this task adds; verified against real output below, not just asserted |

### Payment-grouping verification (real numbers, not asserted)

Truman's own settlement-sweep amount already IS the sum of that day's
purchase proceeds for that merchant, by construction (`_run_settlement`
sweeps the WHOLE pending balance, every day, no partial sweeps --
documented as a "near-tautological" property in `Simulation/docs/
Memory.md`'s Phase 2 section). So the real test of this bridge's grouping
logic is: for a real bridged settlement, does
`sum(payments assigned to it via settlement_payments.csv)` equal that
settlement's own `net_amount`, exactly? Checked directly against the real
end-to-end run below's output CSVs (`financial_system/bridges/
bridge_output_controller/raw/`), 5 real settlements, every one exact:

```
settle_bridge_txn_00000075: net_amount=1376.76  sum_of_5_payments=1376.76  match=True
settle_bridge_txn_00000076: net_amount=1959.58  sum_of_9_payments=1959.58  match=True
settle_bridge_txn_00000f0d: net_amount=357.68   sum_of_3_payments=357.68   match=True
settle_bridge_txn_00001da8: net_amount=1894.75  sum_of_5_payments=1894.75  match=True
settle_bridge_txn_00003492: net_amount=2051.90  sum_of_7_payments=2051.90  match=True
```

And over ALL 1770 bridged settlements in that run, not just these 5: zero
mismatches (`settlement_sum_check_mismatches=0`, `simulation_bridge.py`'s
own transform-time self-check -- every settlement's sweep amount matched
the sum of the payments this bridge assigned to it, exactly, in Decimal
arithmetic), and every settlement had at least one payment assigned to it
(no settlement left orphaned by the grouping logic).

### Real result: Controller decision distribution (verbatim)

Of 1770 bridged settlements, Heimdall's real, unmodified Controller logic
(`reconciliation.controller.run_controller_for_settlement()`,
`investigate=False`, same 4A-only default as `reconciliation/runner.py`'s
own Phase 5 done-check) decided:

```
{'PASS': 1770}
```

**All 1770, 100%.** This is the honest, CORRECT, expected result, not a
gap to fix: `Simulation/` genuinely does not simulate any settlement
discrepancy (no fee/tax that could create a gross-vs-net gap since none
exists, no banking delay/error, no duplicate settlement-payment linkage
inserted). `reconcile_settlement()`'s own real logic (`expected -
actual`, tolerance `Decimal("1.00")`) correctly finds zero discrepancy on
every one of these settlements because there IS zero discrepancy in the
bridged data -- the same honesty standard as Risk's zero-HOLD-verdicts
result and Recovery's single-failure-category result before it. Do not
read "1770/1770 PASS" as evidence Controller is trivial or the bridge is
undertesting it: Controller's real, frozen result on the ACTUAL Heimdall
dataset (91.0% match rate, 555/610, `investigate=False`, same as this
bridge's default -- see "Baseline reproduction" below) is where its real
decision surface (RESOLVE/REVIEW/INVESTIGATE, duplicate-record handling,
fee/partial-refund/currency-conversion cases) actually gets exercised;
this bridge proves the plumbing is real end-to-end, not that Controller's
harder cases got tested here, exactly parallel to how the Risk bridge
section above frames its own zero-HOLD result.

### Baseline reproduction (before and after this task's changes, verbatim)

Canonical Phase 1->2->3 (`build_financial_state()` -> `run_phase2()`
in-process via `entity_resolution.runner`'s `run_phase2` steps ->
`build_graph()`), run against the REAL dataset, both before touching any
bridge code and again after:

```
PHASE 1: PASS  (row_count_failures=0, checksum_failures=0)
PHASE 2: PASS  (0 reference-key violations; step 6 633/633 deterministic bank matches;
                precision=100.00% recall=100.00% F1=100.00% vs ground_truth/entity_resolution_labels.csv)
PHASE 3: PASS  (0 orphaned required relationships, 0 fabricated relationships, 0 provenance gaps)

Risk (financial_system.risk.runner):      precision=100.0% recall=96.3% false-positive-rate=0.0% (tp=26 fp=0 tn=373 fn=1) -- PHASE 6: PASS
Recovery (financial_system.recovery.runner): category accuracy=100.0%; recovery rate 87/87 (100.0%); false-retry rate 57/144 (39.6%) -- PHASE 7: PASS
Controller (financial_system.reconciliation.runner): match rate 555/610 (91.0%); honest-exception rate 47/50 (94.0%) -- PHASE 5: FAIL (unchanged from before this task -- Controller's own existing done-check requires investigate=True/4B for the fee_discrepancy and partial_refund root causes, which this bridge task did not touch or run with)
```

Every one of these numbers is byte-for-byte identical before and after
this task's changes -- confirming the three bridge files touched
(`simulation_bridge.py`, `run_bridge.py`, `test_simulation_bridge.py`,
all under `financial_system/bridges/`) have zero effect on
`financial_system/`'s frozen, already-judged behavior on its own real
dataset. `git diff --stat financial_system/` below confirms only those
three files under `bridges/` changed.

### Honest gaps (Controller-specific)

1. **`fee_amount`/`tax_amount` are fabricated-zero.** Stated above, and
   inert by construction since `reconcile_settlement()` never reads
   either field -- confirmed by reading the function, not assumed.
2. **No settlement discrepancy is ever simulated**, by design --
   `Simulation/` has no fee/tax, banking-delay, banking-error, or
   duplicate-settlement-linkage concept. Every bridged settlement
   reconciles cleanly. This is the honest, correct, expected result given
   the input, not something this task manufactured or should have
   manufactured a fake discrepancy to avoid.
3. **`bank_transactions.csv: utr`/`description` are deterministic
   placeholders**, shaped specifically to make Phase 2 step 6's real
   description-matcher resolve every settlement's `deposited_as` edge via
   its deterministic pass (not its probabilistic fallback) -- this is a
   real exercise of that matcher's real logic, not a bypass of it, but
   the specific placeholder text itself carries no signal beyond identity.
4. **Controller's harder decision surface (RESOLVE / REVIEW / INVESTIGATE,
   duplicate-record handling, the fee/partial-refund/currency-conversion
   root causes) is not exercised by this bridge at all** -- same
   structural ceiling Recovery's README section already names for its own
   domain (only one of seven failure categories ever exercised there).
   `Simulation/` would need to grow some notion of settlement error or
   discrepancy for a future bridge to exercise Controller's remaining
   decision branches; out of scope here.

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
| `transactions.csv: kind == "settlement"` | -> | `settlements.csv`, `bank_transactions.csv`, `settlement_payments.csv` | **REAL, direct** (later addition -- see "Part 3: Controller" above for the full field-by-field table and honest gaps) |
| *(none: `refunds`, `fees`)* | -> | written header-only (0 rows) | Simulation models neither concept at all; written empty so Heimdall's fixed Phase 1 ingestion-step list still runs unmodified end to end |

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
Controller's own real 1770/1770 PASS result above (see "Part 3") extends
this same pattern to all three domains: unmodified Heimdall code, real
decisions, on data honestly never designed to contain the harder cases
each domain also handles.

## New files

- `financial_system/bridges/__init__.py`
- `financial_system/bridges/simulation_bridge.py` -- the transform (Simulation output -> Heimdall raw-CSV schema; now includes real Device data (Part 2) and real Settlement/BankTransaction/settlement_payments data (Part 3))
- `financial_system/bridges/run_bridge.py` -- orchestrates the transform + calls Heimdall's real Phase 1/2/3/Recovery/Risk/Controller functions, unmodified
- `financial_system/bridges/test_simulation_bridge.py` -- tests for the transform itself (7 tests, all passing)
- `financial_system/bridges/README.md` -- this file
- `financial_system/bridges/bridge_output/` -- one real generated run's output from the original Recovery/Risk bridge (raw CSVs + `financial_state.db` + `financial_graph.db`), regenerable by re-running the Part 2 command above
- `financial_system/bridges/bridge_output_controller/` -- one real generated run's output from the Controller follow-on task (same shape, now also including real settlements/bank_transactions/settlement_payments), regenerable by re-running: `python -m financial_system.bridges.run_bridge Simulation/output/bridge_run_controller financial_system/bridges/bridge_output_controller` (simulation run: `python run_simulation.py --seed 42 --population 300 --banks 4 --merchants 20 --days 90 --outdir output/bridge_run_controller`, run from `Simulation/`). Neither `bridge_output*` directory is required to exist for the bridge code itself to work, or committed to git (both are generated artifacts).

No file under `financial_system/`'s existing (non-`bridges/`) code, and no
file under `Simulation/`'s existing engine/world code other than the
explicitly-scoped Device addition (see the main task report / `Simulation/
docs/Memory.md`'s "Device" section), was modified. The Controller
follow-on task modified zero files under `Simulation/` at all -- confirmed
by `git diff --stat Simulation/` returning empty for that task, since
`_run_settlement()`'s existing T+1 per-merchant-per-day batch already
mapped directly onto Heimdall's Settlement concept with no new engine
feature needed.
