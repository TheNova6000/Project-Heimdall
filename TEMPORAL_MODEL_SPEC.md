# Temporal Model Specification

Normative, not explanatory — `TEMPORAL_ONTOLOGY_REVIEW.md` is the evidence
and reasoning; this is the rule set derived from it. Adversarial testing
against Stage 1–4's actual implementation follows in the next section of
this document, per the agreed sequence: spec, then adversarial test, then
(only if warranted) implementation.

## Definitions

| Object | Definition |
|---|---|
| **Event** | An immutable record that something was true, at a specific time, about a specific subject. Has its own identity (`event_id`), never edited, only ever superseded. |
| **State** | A projection of the event log for one subject — "what do we currently believe," derived, never itself a source of truth. |
| **Observation** | What the intelligence layer sees when it queries State at a particular moment. Not a persisted object — a query result. |
| **Finding** | A deterministic interpretation of an Observation (`ReconciliationFact`/`RiskSignals`/`RecoverySignals` today — three instances of one concept, per `ONTOLOGY_REVIEW.md` #7). Zero LLM, always. |
| **Investigation** | An evidence-seeking interpretation, invoked only when a Finding is insufficient to decide. The one object an LLM may write to (`InvestigationResult.narrative`/`.inferences`/`.hypotheses`/`.investigation_confidence`, and nothing else, anywhere). |
| **Verdict** | A domain decision (`AgentVerdict`) — `decision`/`decision_score`/`proposed_action` always agent-computed, never LLM-influenced. |
| **Action** | An authorized, durable request to change the world — has its own identity, its own lifecycle (`PENDING → STARTED → COMPLETED/FAILED/REJECTED`), idempotent by construction. |
| **Outcome** | The observed consequence of an Action, represented as another Event (`ActionOutcomeObserved`) — never inferred, never assumed. |

## Object ownership

| Object | Owning module | May construct it |
|---|---|---|
| Event | `financial_system/events/` | Ingestion (backfill), `action/event_execution.py`, future Reasoning-event emitters |
| State | `financial_state/` (projected, not directly written) | Only the projector (`events/projection.py`, `events/action_projection.py`) |
| Finding | `reconciliation/`, `risk/`, `recovery/` (`deterministic.py`/`signals.py`) | Each domain module, over its own subject type only |
| Investigation | `discovery_adapter/` | Only via `investigate_evidence()` — the sole boundary touching Discovery.AI |
| Verdict | `reconciliation/controller.py`, `risk/risk_agent.py`, `recovery/recovery_agent.py` | Each domain agent, for its own `agent` field value only |
| Action | `action/` | `event_execution.py`, gated on an `ALLOW` `PolicyDecision` |
| Outcome | `action/simulator.py` (today: simulated) | Only as a payload on an `ActionOutcomeObserved` event |

## Event invariants

1. Never updated after insertion (enforced structurally — no `UPDATE` path exists in `EventStore`).
2. `event_type` is a closed-taxonomy value (`events/taxonomy.py`); no free-text types.
3. A correction is a new event of the *same* `event_type`, with `supersedes_event_id` set — never a dedicated `*Correction` type (locked in during the migration design turn).
4. Two competing successors to the same event (`E2.supersedes=E1` and `E3.supersedes=E1`) are never silently resolved — the projection raises `ProjectionConflict`, routed to `REVIEW`, never picked by timestamp/insertion order/UUID.
5. `causation_id`, when set, must reference an event with `occurred_at <= this event's occurred_at` — enforced at write time (`CausationOrderViolation`).
6. Dedup key is type-dependent: `(source, source_event_id)` for externally-sourced events, `idempotency_key` for Action-originated events, no dedup key for pure Reasoning events (harmless to duplicate — they don't drive State).
7. `recorded_at >= occurred_at` is expected but **not currently enforced** — named explicitly as a gap the adversarial test below checks.

## State invariants

1. State is always a pure function of the event log — never edited independently of it, with exactly two sanctioned exceptions, both scoped to command-lifecycle bookkeeping, never business fact: `Action.execution_status` and (as of Stage 4) `payments.status`/`failure_reason`/`captured_at` via `apply_payment_retry_success()`, itself only ever called by `project_action_outcome()`.
2. Rebuilding State from the event log twice must produce identical results (idempotent projection) — proven for the full historical corpus in Stage 1's Gate 1; not yet proven for a log that includes real Action-lifecycle events (checked below).
3. State never gets ahead of the event log — every field on a State row must be traceable to a specific event.

## Attempt semantics (the concrete fix `TEMPORAL_ONTOLOGY_REVIEW.md` converged on — specified here, not yet implemented)

1. Every Payment-subject Observational/Outcome event carries an `attempt` number, starting at `1` for the original backfilled `PaymentCreated`/terminal event.
2. Each real retry's `ActionOutcomeObserved` increments `attempt` for that subject.
3. `payments.status` (State) always reflects the **latest** attempt's outcome; the full attempt history is queryable from the event log via `events_for_subject(payment_id)`, ordered by `occurred_at`.
4. A domain agent reading Payment state should be able to ask both "what is the current status" (State) and "how many attempts, and what happened on each" (event history) — Recovery does not yet do the second; that's the fix this points to, not yet made.

## Observation semantics

1. Not a persisted object. A pure function `observe(state, subject_id) -> Finding-input`, always re-derived, never cached.
2. Because it's a pure function of State, and State is a pure function of Events, an Observation is fully determined by "which events existed as of query time" — which is exactly what makes `as_of` meaningful (below) without needing to persist Observations themselves.

## Finding semantics

1. Zero LLM, always — enforced structurally today (verified: no Finding-producing function imports anything from `discovery_adapter` or touches an LLM client).
2. Deterministic given identical State — verified property, not just design intent (`TEMPORAL_ONTOLOGY_REVIEW.md` #8).
3. Never independently persisted; never goes "stale" because it's never cached (`TEMPORAL_ONTOLOGY_REVIEW.md` #6) — this invariant breaks the moment Finding-computation is ever cached for performance, and must be revisited if that happens.

## Temporal validity

1. Findings have no independent temporal validity — they inherit it entirely from the State they were computed against.
2. Verdicts and Investigations, when persisted (Phase 4's JSONL batches), should carry the `event_id`(s) of the State snapshot they were computed from — **not currently done**, named as a gap, not fixed here.
3. A Verdict computed against State-as-of-T1 is not automatically invalid at T2 — it's a true historical fact ("this was our decision, given what we knew then"). What changes at T2 is only that a *fresh* Verdict computation may now differ, per the `as_of` mechanism below.

## `as_of` projection semantics (elevated to a first-class principle, not yet implemented)

1. `project(events, as_of=T) -> State` — the same projection logic already proven in Stage 1, parameterized by a cutoff timestamp instead of always defaulting to "all events, i.e. now."
2. Filter rule: include only events with `occurred_at <= T`; apply the same non-superseded / latest-attempt logic as the unparameterized projection, restricted to that filtered set.
3. Does not require a second graph or a second State store — one event log, many `as_of` views, the same principle Discovery.AI's own (unimplemented) View layer already claimed for relationship-family projection, applied to time instead.
4. **Not implemented.** `financial_graph/builder.py::build_graph()` and `events/projection.py::project()` currently have no `as_of` parameter.

## Re-entry semantics

1. An Outcome event causes re-entry only via a deterministic pattern match over the event stream (`ActionOutcomeObserved` + `verification_result == "FAILURE"` → `_investigate_failure()`), never via an LLM decision about whether to re-investigate.
2. Re-entry means: rebuild/reproject State, then re-run the *same*, unmodified domain-agent Finding/Verdict logic against it — never a special "re-entry" code path with different rules (verified in Stage 4 Gate 3: the fresh Recovery verdict came from the exact same `run_recovery_for_payment()` call every other Recovery verdict uses).

## Idempotency relationship

1. Idempotency (Action) and event dedup (Event) are related but distinct mechanisms, deliberately: an Action's `idempotency_key` protects against *re-requesting the same command*; an Event's `(source, source_event_id)` dedup protects against *re-recording the same external fact*. A single logical retry produces one of each, not one mechanism serving both roles.
2. An idempotency key scoped as `{subject}:{attempt}:{action_type}` (today's scheme, `action/loop.py`) is attempt-scoped by construction — verified below to correctly permit two *genuinely distinct* retry attempts on the same payment without collision.

## Provenance requirements

1. Every Event traces to `source` + (`source_event_id` when externally sourced) — no exceptions.
2. Every State row traces to the Event(s) that produced it via `_provenance()`'s reconstruction from the event's own `source`/`source_event_id` (Stage 1) — verified exact-match against direct ingestion.
3. Every Finding carries the entity ids (not yet: event ids) it was computed from.
4. Gap, named not fixed: Verdicts/Investigations don't yet carry the specific event id(s) their underlying State reflected — see Temporal Validity #2.

## Explicitly out of scope

- Double-entry ledger / value-conservation accounting (standing decision, unchanged).
- Live gateway integration, real concurrency, a durable-workflow engine, `schema_version` upgrade tooling (all per `MIGRATION_DESIGN.md` §11, unchanged).
- Rewriting `recovery_agent.py` or any domain agent to consume attempt history — named as the destination, not built now.
- Implementing `as_of` — specified above, not built now.

---

## Adversarial test results

Run directly against Stage 1–4's actual code (`financial_system/events/adversarial_test.py`)
where the capability already exists; analyzed against the spec, not
run, where it doesn't — the gap stated plainly, not glossed over.

| Scenario | Result |
|---|---|
| Duplicate event | **PASS** — second `append()` with the same `(source, source_event_id)` raises `DuplicateEvent`. |
| Out-of-order event | **PASS** — an event whose `causation_id` points to a chronologically later event raises `CausationOrderViolation`. |
| Late event | **PASS** — a 3-day `occurred_at`/`recorded_at` gap is accepted and preserved exactly on read-back. |
| Retry after timeout | Already proven — Phase 10/Stage 3/4's real `technical_failure`/`timeout` categories. |
| Successful retry | Already proven — Stage 4 Gates 1–3 (real payment, real status transition, real re-observation). |
| Failed retry | Already proven — Stage 4 Gate 5, Stage 3's whole flow. |
| Two retries | **PASS, and a real distinction confirmed**: this is *not* what Phase 10's loop actually does today (1 retry + 1 deterministic escalation, never 2 real retries) — so this test constructs two genuine `RETRY_PAYMENT` attempts directly against `execute_action_with_events()` and confirms the attempt-scoped idempotency key (`{subject}:{attempt}:{action}`) produces two distinct `Action` rows and two distinct `ActionOutcomeObserved` events, no collision. |
| Refund after success | **Analyzed, not run: no issue found.** `RefundRecorded`/`add_refund()` key on `payment_id` alone, never on attempt number or current status — a refund projects identically regardless of whether the payment succeeded on its original attempt or a later retry. This scenario doesn't actually stress the attempt-conflation gap. |
| Refund after retry | Same conclusion as above, same reasoning. |
| Reversal after settlement | **Not run — no code path exists to construct it, and no dedicated event type exists for it.** The generic correction mechanism (`supersedes_event_id`, spec'd in Event invariants #3) should cover it in principle — a new `SettlementReceived` event superseding the original — but this is untested, same "built but unexercised" category as Phase 2's probabilistic matching. |
| Restart between events | Already proven — Stage 4 Gate 2 (fresh connection, same file, transition read back correctly). |
| Same event replayed | **PASS** — the full event log projected into two independent, fresh stores produces an identical `payments.amount` sum (`5761505.36` both times), confirming Stage 1 Gate 1's idempotent-replay property still holds. |
| `as_of` before/after an outcome | **Cannot be tested — the capability doesn't exist.** `build_graph()`/`project()` have no `as_of` parameter today. This is the one scenario in the list that isn't a passed/failed test but a confirmed, named gap — exactly the concrete next implementation step this whole review sequence points to. |

**One additional gap this test suite found and reports honestly, not in
the original thirteen**: `recorded_at >= occurred_at` (Event invariants
#7) is **not currently enforced** — the store accepts an event claiming to
have been recorded *before* it occurred. Confirmed directly: an event with
`occurred_at = now`, `recorded_at = now - 1h` is accepted without error.
Named in the spec as expected-but-unenforced; this test makes that
concrete rather than theoretical.

### What survived, what didn't, what's still open

Ten of thirteen named scenarios pass or are already proven by real code.
Two (refund after success/retry) turn out not to stress the ontology gap
at all — a legitimate, useful negative result, not a shortcoming of the
test. One (reversal after settlement) is genuinely untested. The
specification's central claim — `as_of` projection as a first-class
principle — is not yet implemented, and this document doesn't pretend
otherwise. Per the agreed sequence, that's now the precise, evidence-backed
target for whenever implementation is taken up next: `as_of` projection
first (it's the one gap blocking a real test, not just an unexercised
path), attempt-unification second (it's what actually fixes Gate 3's
confused reasoning, not just "not RETRY").
