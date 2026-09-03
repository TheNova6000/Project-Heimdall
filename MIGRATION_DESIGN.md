# Migration Design — Event Store + Action, over the existing Phase 0–10 system

Written before any code, per the explicit sequencing agreed across
`ARCHITECTURE_REVIEW.md` → `ONTOLOGY_REVIEW.md` → this document: semantics
first, then schema, then migration strategy, then code. This document is
strategy. No implementation happens until it's reviewed.

**Governing principle, stated once, applied everywhere below:** the Event
Store becomes the historical source of truth; `financial_state`/the graph
remain queryable *projections* of it, not a second source of truth. Nothing
about Phases 1–10's actual results changes — this is additive infrastructure
underneath them, proven equivalent by the tests in §8 and §10 before
anything is allowed to depend on it.

## 1. Event schema

```
Event
├── event_id            str, UUID, ours, globally unique
├── event_type           str, from the closed taxonomy in §2
├── schema_version        int, starts at 1 -- see §2's note on payload discipline
├── subject_id
├── source                 str -- which agent/system produced this (§11 of the semantics turn)
├── source_event_id         str | None -- external dedup key (§4)
├── occurred_at              datetime -- when it was true
├── recorded_at               datetime -- when we learned it (== occurred_at for all
│                              Stage-2 backfilled historical events -- see §7)
├── payload                    dict
├── correlation_id              str -- the case (see §1a)
├── causation_id                 str | None -- the specific prior event that produced this one
└── supersedes_event_id           str | None -- set only on a correction (§3)
```

**1a. `correlation_id` vs. `case_id`.** Per your refinement: not a permanent
identity. `correlation_id = case_id` initially and for the entire scope of
this migration (nothing in Phases 5–10 needs a case to fork into multiple
correlated subprocesses yet) — but they're separate fields from day one so
that distinction is available without a later schema change. `Case` gets its
own table (§6), not derived from `correlation_id` grouping alone.

## 2. Event taxonomy (closed, not open-ended)

Kept closed for the same reason `relation_types.py` and the four-kinds-of-
intelligence table are closed: a fixed vocabulary is auditable, an
open-ended `event_type: str` free field is not.

| Category | Types | Source |
|---|---|---|
| **Observational** | `PaymentCreated`, `PaymentCaptured`, `PaymentFailed`, `OrderCreated`, `SettlementReceived`, `BankTransactionRecorded`, `RefundRecorded`, `FeeRecorded` | `gateway_simulator` (Stage 2/3) or the original ingestion agents (Stage 2 backfill) |
| **Reasoning** | `EntityMatchResolved`, `VerdictProduced`, `PolicyDecided`, `InvestigationOpened`, `InvestigationConcluded`, `ConflictDetected`, `CompoundCaseCreated` | the producing agent (`controller_agent`, `risk_agent`, `recovery_agent`, `policy_engine`, `discovery_adapter`, `orchestrator`) |
| **Action** | `ActionRequested`, `ActionExecutionStarted`, `ActionOutcomeObserved` | `action_executor` |

Only `event_type` values from this table are valid; the event store rejects
anything else at write time (mirrors `relation_types.py`'s own enforcement
pattern).

**`schema_version` discipline**: payloads must be extended additively (new
optional keys only, per `Rules.md`'s existing "additive only" rule for
`relation_types.py`) within a version; a breaking payload change bumps
`schema_version` and the projection code must keep an explicit case for
every version it might replay. We are not building a version-upgrade/
transform framework in this migration (§11) — just the discipline that
makes one buildable later without re-litigating old events.

## 3. Immutability / correction rules

- No `UPDATE` is ever issued against the events table — enforced at the
  repository layer exactly like `financial_state`'s existing insert-only
  discipline (Phase 1's own precedent, and Discovery.AI's own
  `Claim.superseded_by`, verified at `backend/evidence/models.py:64-67`).
- A correction is a **new event of the same `event_type`**, with
  `supersedes_event_id` set to the event it revises and `causation_id` set
  to whatever triggered the correction. See the `SettlementCorrection`
  note above for why this isn't a separate type.
- **Your caveat, made concrete**: "the latest non-superseded event" is not
  automatically authoritative. Projection rule: an event is *excluded* from
  current-state if some other event's `supersedes_event_id` points at it.
  If **two different events both supersede the same original** (a genuine
  branching correction — two independent sources both claiming to correct
  the same fact differently), the projection does **not** silently pick a
  winner by `occurred_at` or any other heuristic. It raises a
  `ProjectionConflict` for that subject and routes it to `REVIEW` — the
  exact same "don't flatten a disagreement" discipline Phase 8's
  `detect_conflicts()` already proved out at the verdict layer, now applied
  one layer down, at the fact layer.

## 4. Deduplication rules

Type-dependent, not universal:
- **Observational events**: dedup key is `(source, source_event_id)`.
- **Action events**: dedup key is `idempotency_key` — the verified Stripe
  mechanism (same key + same params → return the cached result; same key +
  different params → reject).
- **Reasoning events**: no dedup key needed. Re-running `reconcile_settlement()`
  twice and appending two `VerdictProduced` events is harmless — these
  events don't drive world-state projection (§6), only the case-trail
  projection, which can tolerate a benign duplicate observation of "we
  computed this verdict" without consequence. Dedup matters where a
  duplicate would cause a duplicate real-world or state effect; pure
  reasoning-trail events don't have that failure mode.

## 5. Ordering rules

- Projection order is **always** `occurred_at`, never `recorded_at` or
  insertion order.
- `recorded_at` is preserved for a different purpose: measuring how stale
  our belief was (`recorded_at - occurred_at`), a real operational metric
  worth surfacing in the eventual demo, not a discarded field.
- **New invariant, worth enforcing at write time**: `causation_id`, when
  set, must reference an event with `occurred_at <= this event's occurred_at`.
  An event cannot be caused by a future event. Cheap to check on insert,
  catches a real class of construction bugs early.

## 6. Projection rules

Three separate projections read the same event log, never three separate
stores:

- **Financial State projection**: for each subject, take the
  non-superseded Observational event with the latest `occurred_at`;
  extract its payload's status-relevant fields. This is what
  `financial_state`'s tables become — a materialized view, rebuildable at
  any time, exactly as disposable as it already is today (Phase 1 already
  deletes and rebuilds this file every run).
- **Financial Graph projection**: unchanged in concept — built *from* the
  Financial State projection, same as Phase 3 today. A projection of a
  projection, which is fine; nothing about `financial_graph/builder.py`'s
  actual logic needs to change.
- **Case-trail projection**: for a given `correlation_id`, every event
  ordered by `occurred_at` — this is what reconstructs Verdict/
  PolicyDecision/Action/Investigation history "from the database," not from
  whatever a Python process happened to hold in memory. This is the
  projection that directly fixes the central finding from
  `ARCHITECTURE_REVIEW.md`.

## 7. Historical-event generation (Stage 2)

For the existing Phase 0 CSVs: generate the events that *would* have been
recorded had this event-sourced system existed from the start
(`PaymentCreated` from `payments.csv`, `SettlementReceived` from
`settlements.csv`, etc.), with `occurred_at` taken from the CSV's own
timestamp fields. **`recorded_at = occurred_at` for every Stage-2
backfilled event** — we have no genuine "we learned about it later" data
for historical rows, and pretending otherwise would fabricate a signal.
Only Stage 3 onward (real `ActionOutcomeObserved` events) will have a
genuine `recorded_at - occurred_at` gap.

## 8. State-compatibility test (Stage 1 gate)

The literal acceptance test before Stage 1 is allowed to be considered
done: run both pipelines against the identical Phase 0 CSVs — today's
direct ingestion (Phase 1, unchanged) and the new event-store-then-project
path — and diff every `financial_state` table row-for-row. Zero
differences allowed. This is a real, automated test, not a visual
inspection, matching this project's own standing rule (`Rules.md`: never
report a metric that wasn't actually computed).

## 9. Action migration (Stage 3)

`execute_action()` stops returning a bare `(bool, str, str)`. New shape:

```
PolicyDecision (ALLOW)
   → write ActionRequested event (correlation_id=case_id, causation_id=PolicyDecided event)
   → create Action row (execution_status=PENDING)
   → write ActionExecutionStarted event; Action.execution_status=EXECUTING
   → call the simulator (unchanged from Phase 10 -- still the one place
     ground_truth/recovery_labels.csv is read, still never read by agent logic)
   → write ActionOutcomeObserved event, payload carries the result
   → Action.execution_status=COMPLETED (mutated in place -- tracking the
     command's own lifecycle, per the PaymentIntent-style hybrid agreed
     last turn)
```

**Only `ActionOutcomeObserved` feeds the Financial State projection.**
`ActionRequested`/`ActionExecutionStarted` never touch world-state — this
is the mechanical enforcement of "Action commands the external world, it
doesn't update our state directly."

## 10. Closed-loop replay test (Stage 4 gate, the big one)

Two independent tests, both required:

1. **State replay**: delete `financial_state.db` and `financial_graph.db`.
   Replay the Event Store through the projections in §6. The result must
   be identical to the pre-deletion state. (This generalizes §8's test to
   apply after Stage 3/4 too, not just the Stage 1 backfill.)
2. **Case replay**: pick a payment whose recovery loop ran through a
   failure→escalate cycle in Phase 10. Write a *second*, independent
   script that reconstructs "what did Recovery decide, what did Policy
   decide, what Action was taken, what was observed" **purely by querying
   events grouped by `correlation_id`/`causation_id`** — no access to the
   original run's in-memory `ActionCase`/`CompoundCase` objects. Diff that
   reconstruction against what the original run actually produced. This is
   the test that would catch a projection that's subtly lossy, which §8's
   pure-state test wouldn't necessarily surface.

If both pass: "the database contains the loop" stops being a claim and
becomes a verified property, the way every other headline number in this
project has been.

## 11. Explicitly out of scope for this migration

Named here so nothing gets scope-crept in during implementation:

- **No live gateway integration.** Action's external effect stays
  simulated (`action/simulator.py`'s existing, documented boundary is
  unchanged — it becomes the thing that produces `ActionOutcomeObserved`'s
  payload, nothing more).
- **No double-entry ledger.** Standing decision from two turns ago: no
  demonstrated failure justifies it yet.
- **No real concurrency or distributed event bus.** Single-process,
  synchronous replay only. The schema is designed to *tolerate*
  out-of-order arrival (§5); nothing in this migration will actually
  produce it, same "designed for it, honestly unexercised" posture as
  Phase 2's probabilistic matching.
- **No schema-version upgrade/transform framework.** `schema_version`
  exists and payloads are additive by discipline (§2); building tooling to
  auto-migrate an old payload shape to a new one is real infrastructure for
  later, not this pass.
- **No Kafka or durable-workflow engine.** SQLite already gives us
  replay-for-free once the log is real (§7's point about this codebase
  having always been "replay-friendly in spirit"). The concept is adopted;
  the infrastructure is not.

## Stage order, restated plainly

1. Event infrastructure, zero behavior change, gated by §8's test.
2. Historical backfill from the Phase 0 CSVs (§7), rebuild State/Graph
   entirely from events, still gated by §8.
3. Action migrated to the event-producing shape (§9).
4. The loop closes for real — a verified outcome feeds a new observation
   that Controller/Risk/Recovery can act on — gated by §10's two tests.

Nothing in Phases 5–10's existing code changes its *decisions* at any
stage; every existing benchmark (99.5% match rate, 96.3% risk recall, the
Phase 9 boundary tests, the Phase 10 required cases) must still pass
identically after each stage, or that stage isn't done.

## Stage 1 (+2) — ✅ DONE

`financial_system/events/`: `models.py`, `taxonomy.py` (closed set, per §2),
`store.py` (insert-only, dedup + causation-order enforced at write time),
`backfill.py` (Stage 2's historical generation), `projection.py`,
`runner.py` (both gates).

**Gate 1 (§8) result**: every transactional table (`orders`, `payments`,
`settlements`, `settlement_payments`, `bank_transactions`, `refunds`,
`fees`) matches the unchanged direct-ingestion baseline row-for-row, after
excluding exactly three identity-artifact columns
(`prov_ingestion_run_id`, `prov_ingested_at`, and `settlement_payments`'
autoincrement `surrogate_id`) — none of them business facts. **PASS.**

**Gate 2 (§10, state half) result**: Controller 607/610, Risk fraud_ring
recall 26/27 + benign FPR 0/16, Recovery rate 87/87 — all run fresh against
the event-projected graph, all identical to the documented Phase 5/6/7
baselines. **PASS.**

Two real bugs found and fixed while proving this, both about provenance
fidelity, not business logic:
1. `payments.csv` produces two events per row (`PaymentCreated` + a
   terminal event) sharing one CSV row number — the dedup key needed
   `event_type` folded in, or the second event looked like a duplicate of
   the first.
2. `settlement_payments` rows were initially given their *parent*
   `SettlementReceived` event's provenance — wrong, since a link's true
   provenance is its own row in `settlement_payments.csv`, not its
   settlement's row in `settlements.csv`. Fixed by carrying each link's own
   row number through the event payload (`payment_links`, not a flat
   `payment_ids` list) so `projection.py` reconstructs the exact composite
   id (`f"{settlement_id}:{payment_id}:row{N}"`) the original ingestion
   path uses.

## Stage 3 — ✅ DONE

`financial_system/action/`: `models.py` (added `Action`, the one object
explicitly allowed to mutate a field in place — `execution_status`, tracking
the command's own lifecycle, never the financial world's), `action_store.py`
(the one store with a real `UPDATE`, scoped exactly to that field),
`event_execution.py` (`execute_action_with_events()` — durable, idempotent,
crash-safe), and `run_action_loop_v2()` added to `loop.py` alongside the
original, untouched `run_action_loop()`.

**Behavioral preservation**: ran both the original and the event-emitting
loop across all 160 failed payments — **0/160 mismatches** in `case_status`
or attempt count. Phase 10's exact numbers (68 RESOLVED, 57 REVIEW, 35
ESCALATE, 19 second attempts) are reproduced through the new path.

**Idempotency gates, all PASS:**
- **Gate A** (same request twice): second call returns the cached result;
  exactly 1 `ActionOutcomeObserved` event recorded, not 2.
- **Gate B** (same key, different parameters): second call rejected
  outright; still exactly 1 `ActionOutcomeObserved` event.
- **Gate C** (simulated crash), two sub-cases: **C1** — `ActionRequested`
  + `ActionExecutionStarted` recorded, no outcome anywhere — refuses to
  re-execute rather than guessing. **C2** — the outcome *was* recorded
  before the simulated crash, only `Action.execution_status` was never
  advanced — recovers it from the event log instead of re-executing. Both
  produce zero duplicate `ActionRequested` events.

The critical invariant (`ActionRequested`/`ActionExecutionStarted` never
touch financial state; only `ActionOutcomeObserved` could) holds
structurally right now because nothing reads Action events back into
`financial_state` yet — no write-back path exists until Stage 4. Stage 4 is
exactly where this invariant stops being true-by-absence and starts needing
to be true-by-design; the event separation built here is what makes that
possible.

## Stage 4 — ✅ DONE

`financial_system/events/action_projection.py` (`project_action_outcome()`
— the ONE path from an Action-lifecycle event to financial state,
structurally, not by convention: its first line makes `ActionRequested`/
`ActionExecutionStarted` incapable of reaching the mutation) +
`financial_state/store.py::apply_payment_retry_success()` (the one
sanctioned Payment mutation, mirroring `Action.execution_status`'s own
precedent) + `action/stage4_runner.py`. Runs entirely against an isolated
`financial_state_stage4.db` — the shared baseline every other phase depends
on was never touched.

**All 5 gates PASS:**
- **Gate 1 (projection boundary)**: `ActionRequested`/`ActionExecutionStarted`
  events produce zero mutation; the same payment's `ActionOutcomeObserved(SUCCESS)`
  flips `status: failed -> success`.
- **Gate 2 (persistence)**: reopened the state store on a fresh connection
  (simulating a restart) — the transition was read back correctly, not
  recovered from anything held in memory.
- **Gate 3 (re-entry)**: rebuilt the graph from the mutated state;
  `classify_event_types()` no longer reports `PAYMENT_FAILED` for the
  recovered payment, and a fresh Recovery verdict no longer proposes
  `RETRY`. The new observation reaches the orchestrator for real, not a
  dead-end callback.
- **Gate 4 (behavioral preservation)**: inherited from Stage 3's 0/160
  result — nothing in Stage 4 touches `run_action_loop`/`run_action_loop_v2`
  or any agent's decision logic, only adds a projector strictly downstream.
- **Gate 5 (no phantom facts)**: neither "no `ActionOutcomeObserved` exists
  yet" nor "an observed `FAILURE` exists" produces any state transition —
  the C1 lesson from Stage 3, carried into world state.

**One honest rough edge, not fixed, recorded instead**: Gate 3's fresh
Recovery verdict reads `decision=INVESTIGATE`, `reason="unrecognized
failure_reason=None"` rather than something like "already succeeded,
nothing to recover." It satisfies the gate (not `RETRY`), but the stated
reason is a byproduct of `recovery/signals.py` never having been designed
to see a payment that used to be failed — exactly the "this system has
never had to represent before/after" finding from `ONTOLOGY_REVIEW.md`,
now observed directly rather than argued abstractly. Left alone
deliberately: fixing it means editing `recovery_agent.py`, and no agent
code changes anywhere in this migration.

The projection stayed narrow throughout, per this stage's explicit design
rule: `project_action_outcome()` does exactly one thing — turn one event
into one state transition — and calls no agent, no policy, no investigation.
Everything downstream of that (Gate 3's fresh Recovery verdict) happens via
an entirely separate call, on a freshly rebuilt graph, exactly as designed.
