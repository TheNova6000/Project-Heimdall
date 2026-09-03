# Temporal Adversarial Review

Written after the write-boundary hardening checkpoint, per the user's
explicit direction, to answer a different question than
`ONTOLOGY_REVIEW.md`, `TEMPORAL_ONTOLOGY_REVIEW.md`, and
`TEMPORAL_MODEL_SPEC.md` did. Those answered *what is the model* and *what
should the model guarantee*. This document answers:

> **Does the implemented temporal model actually survive hostile
> sequences of events, state transitions, replay, and re-entry?**

Every claim below is one of three kinds, marked explicitly, never blended:

- **PROVEN** -- executed just now against the real code (this session or a
  cited prior one), output shown or referenced by exact numbers.
- **ANALYZED** -- reasoned from reading the actual current implementation,
  not executable because the required path doesn't organically exist in
  this system as built (stated precisely why).
- **UNSUPPORTED** -- the architecture has no legitimate representation for
  the scenario at all (usually: the closed taxonomy structurally rejects
  it).

Two runners back this document with real output: the pre-existing
`financial_system/events/adversarial_test.py` (8 gates, all PASS) and the
new `financial_system/events/temporal_adversarial_runner.py` (6 gates,
all PASS) written for this review. Nothing below is asserted without one
of these two runners, an existing Stage/Phase runner, or a direct grep of
the actual source standing behind it.

## A. Event history

| Scenario | Status | Evidence |
|---|---|---|
| Duplicate event replay (same `source`/`source_event_id`) | **PROVEN** | `adversarial_test.py` gate 1 |
| Same `event_id`, different payload | **PROVEN** | `temporal_adversarial_runner.py` A1 -- rejected via the PK constraint, distinct mechanism from the dedup index, same outcome: original event untouched |
| Out-of-order events (causation pointing to the future) | **PROVEN** | `adversarial_test.py` gate 2 |
| Late events (occurred long before recorded) | **PROVEN** | `adversarial_test.py` gate 3 |
| Impossible timestamps (`recorded_at < occurred_at`) | **PROVEN** | `adversarial_test.py` gate 6 -- rejected at `EventStore.append()`, event count unchanged |
| Naive/aware timestamp mixing | **PROVEN** | `adversarial_test.py` gate 7 -- both normalize to the identical stored instant |
| Event replay after restart | **PROVEN** | `temporal_adversarial_runner.py` A2 (EventStore itself, new connection) + `adversarial_test.py` gate 5 (projection, run twice) + Stage 4 Gate 2 (FinancialStateStore) -- all three storage layers independently proven to survive a simulated restart |
| Identical events arriving twice | **PROVEN** | same as duplicate event replay above -- one scenario, not two |

No gaps found in this layer. This is the most heavily tested boundary in
the system, appropriately -- it's the one everything else is built on.

## B. Attempt history

| Scenario | Status | Evidence |
|---|---|---|
| attempt 1 FAILURE, attempt 2 FAILURE, attempt 3 SUCCESS | **PROVEN at the projection layer only; UNSUPPORTED through the real pipeline** | See below |
| attempt 1 SUCCESS, attempt 2 requested (RETRY against an already-resolved payment) | **PROVEN** | `temporal_adversarial_runner.py` B2 |

**The three-attempt sequence, precisely stated.** `action/simulator.py::simulate_gateway_response()`
reads exactly one `retry_would_succeed` boolean per `payment_id` from
`recovery_labels.csv` (`_recovery_outcomes()`, `lru_cache(maxsize=1)`)
and returns the same value on every call. There is no way, through
`run_action_loop_v2` + the real simulator, for two retries on the *same*
payment to observe different outcomes -- the environment being simulated
is stateless per payment by construction. A genuine FAIL-FAIL-SUCCESS
sequence for one payment is therefore **not reachable through the real
pipeline as built**, and manufacturing one by mocking the simulator would
be exactly the kind of "papered over" result this review exists to avoid.

What's real and provable instead: whether `projection.py`'s own merge
logic (the "latest `ActionOutcomeObserved` wins" rule added for `as_of`)
correctly derives the right final state from a 3-attempt sequence,
independent of how those events were produced. `temporal_adversarial_runner.py`
B1 appends three `ActionOutcomeObserved` events directly (attempt 2:
FAILURE, attempt 3: FAILURE, attempt 4: SUCCESS -- numbered per
`ATTEMPT_MODEL_SPEC.md`'s convention, attempt 1 being the original
failure) and confirms the projected payment resolves to `status=success,
failure_reason=None`. This proves the *projection* logic generalizes
correctly beyond the 2-attempt case already proven in `attempt_runner.py`;
it does not prove the *simulator* can produce this sequence, because it
can't. Recorded as a named limitation of the simulator, not the temporal
model.

**attempt 1 SUCCESS, then a retry is requested anyway.** This is
organically reachable -- nothing stops a caller from invoking
`run_action_loop_v2` a second time on an already-resolved payment.
`temporal_adversarial_runner.py` B2 does exactly that (using the same
success-via-retry payment from the attempt-unification checkpoint) and
shows what actually happens: Recovery's status check (added for attempt
unification) returns `DO_NOT_RETRY`; Policy's pre-existing
`R10_RECOVERY_DO_NOT_RETRY_ALLOW` rule (written for the sibling-success
case, unmodified, now also covers this one) maps that to `ALLOW` with
`authorized_action=NONE`; `event_execution.py`'s `action_taken.startswith("RETRY")`
guard is then False, so `verify_retry()` -- the one function that would
touch the (simulated) gateway -- is never called. An `Action` row and an
`ActionOutcomeObserved` event *are* recorded (`action_taken=NONE,
verification_result=None`), so the call is not silently dropped -- it's
answered honestly, just without ever attempting a duplicate charge. This
is a real, previously-unverified emergent property of composing the
attempt-unification fix with a Policy rule that already existed for an
unrelated reason.

Also worth stating precisely, because it's the one place this review
found a genuine, still-open gap: nothing in `EventStore.append()`
enforces "exactly one outcome per attempt" (`ATTEMPT_MODEL_SPEC.md`
question 7). Two `ActionOutcomeObserved` events with the same
`attempt_number` would both be accepted. Not fixed here -- already
explicitly parked, in both `ATTEMPT_MODEL_SPEC.md` and the `as_of`
report, as a write-boundary invariant for a future checkpoint, alongside
`recorded_at >= occurred_at` (which *has* now been closed).

## C. Projection

| Scenario | Status | Evidence |
|---|---|---|
| `project(events)` deterministic across independent connections | **PROVEN** | `temporal_adversarial_runner.py` C1 -- 1000 payment rows, two fully independent `EventStore`/`FinancialStateStore` connections to the same files, identical output |
| `project(events, as_of=T)` consistent across arbitrary cut points | **PROVEN** | `asof_runner.py` gates 1-4 (before/at/after/current) + `attempt_runner.py` scenario 4 (mid-sequence) + `temporal_adversarial_runner.py` C1 (as_of=now, at scale, cross-connection) |
| `project(events)` (no `as_of`) equals incrementally-applied state | **PROVEN** | Stage 1 Gate 1, re-run this session: baseline (direct CSV ingestion) vs. projected, all 7 tables match exactly (1000/1000 payments, 610/610 settlements, 826/826 settlement_payments, etc.) |
| A late-arriving event retroactively changes what `as_of=T` returns, for a fixed `T` | **PROVEN** | `temporal_adversarial_runner.py` G |

The last row is the one genuinely new finding in this section, worth
stating as a property rather than a bug: **`as_of=T` is not a fixed
historical fact until every event with `occurred_at <= T` has actually
been recorded.** G proves this directly -- the same `as_of=T` query
returns "no refund" before a legitimately late-arriving `RefundRecorded`
event (`occurred_at` before `T`, `recorded_at` long after -- itself a
valid event per section A) is appended, and "refund present" after,
without `T` ever changing. This is correct, expected event-sourcing
behavior (it's the entire reason `recorded_at` exists as a field separate
from `occurred_at`), but it means "the state as of T" is itself a
statement relative to *what has been recorded so far*, not an eternal
constant -- a caller storing an `as_of=T` snapshot and treating it as
permanently authoritative would be wrong if late data can still arrive
for that window. No code change follows from this; it's a property to
know about, not a defect.

## D. Re-entry

| Check | Status | Evidence |
|---|---|---|
| A fresh reasoning pass genuinely reads the new world, not stale process state | **PROVEN** | Stage 4 Gate 3 + `attempt_runner.py` scenario 1 (fresh `GraphRepository`, built from a distinct `.db` file, into a fresh `run_recovery_for_payment()` call) + `temporal_adversarial_runner.py` B2 (a *second* fresh graph + fresh loop call, same payment) |
| No hidden in-process cache could make a "fresh" call stale | **PROVEN** | grep of the entire `financial_system/` tree for `lru_cache`/`@cache`: exactly one hit, `action/simulator.py::_recovery_outcomes()` -- a static read of ground-truth CSV that never depends on world state, so it carries no staleness risk. No other caching exists anywhere in the codebase. |

Re-entry was the layer this whole migration was originally built to prove
(Stage 4's entire purpose), and it holds under a second, independent
re-entry in this review (B2's second `run_action_loop_v2` call), not just
the first one Stage 4 checked.

## E. Epistemic boundary

Attacking `WORLD FACT ≠ OBSERVATION ≠ INFERENCE ≠ HYPOTHESIS ≠ VERDICT`.

| Check | Status | Evidence |
|---|---|---|
| `PolicyDecision` has no field for `investigation_confidence` | **PROVEN** | `policy/engine.py:27`, unchanged; `policy/runner.py` gates 4 and 5 re-run this session, still PASS -- `investigation_confidence=0.99` provably does not authorize a `decision_score=0.20` action |
| Discovery.AI cannot write to financial state or the event log | **PROVEN BY CONSTRUCTION, not merely observed** | grep of `financial_system/discovery_adapter/` for `FinancialStateStore`, `EventStore`, `add_payment`, `events.append`: zero matches. The module has no import, no reference, no code path capable of writing either store -- this isn't a convention Discovery.AI happens to follow, it structurally cannot do otherwise. |
| An investigation's narrative/confidence stays audit-only, never authorizes | **PROVEN** | Same as the `PolicyDecision` row -- `reason` text is Discovery.AI's; `decision`/`decision_score`/`proposed_action` are always the deterministic agent's own, per `verdict.py`'s field ownership, unchanged throughout this entire migration |
| The Reasoning layer of the event taxonomy (`VerdictProduced`, `PolicyDecided`, `InvestigationOpened`/`Concluded`, `ConflictDetected`, `CompoundCaseCreated`, `EntityMatchResolved`) is actually event-sourced | **ANALYZED -- confirmed NOT implemented** | grep across the entire `financial_system/` tree: these six type names appear only in `taxonomy.py`'s own set literals. No code anywhere ever constructs or appends one. Verdicts remain exactly what `TEMPORAL_ONTOLOGY_REVIEW.md` question 10 already found them to be: transient, recomputed-on-demand function results (plus Phase 4's separate JSONL batch persistence for investigations) -- never durable events. |

The last row is this review's most consequential finding, and it's a
scope confirmation, not a bug: the migration that started at
`MIGRATION_DESIGN.md` event-sourced the **Observational** and **Action**
layers completely, and defined the **Reasoning** layer's taxonomy up
front -- but never implemented emitting it. `as_of` projection, attempt
unification, and the write-boundary hardening all operate correctly and
completely on the two layers that were actually built. A question like
"what did Recovery decide about this payment as of last Tuesday" cannot
be answered by `as_of` today, because no `VerdictProduced` event has ever
existed to be `as_of`'d -- only "what was the payment's state as of last
Tuesday" can be answered, which is what was actually specified and built.

## F. Action boundary

| Scenario | Status | Evidence |
|---|---|---|
| `ActionRequested` + `ActionExecutionStarted`, no outcome yet -- world unchanged | **PROVEN** | Stage 4 Gate 1, re-run this session: neither event mutates state, status unchanged through both |
| `ActionOutcomeObserved` -- exactly one permitted transition occurs | **PROVEN** | Stage 4 Gate 1 (SUCCESS -> exactly one status flip) + Gate 5 (FAILURE -> confirmed zero transitions, re-run this session) |

No gaps found in this layer either -- it was Stage 4's own explicit
purpose and both directions (started-but-not-observed, and
observed-but-failed) are independently proven.

## The hardest scenario, walked step by step

```
PaymentCreated
      |
PaymentFailed #1
      |
Recovery -> RETRY
      |
ActionRequested
      |
ActionExecutionStarted
      |
SUCCESS
      |
PaymentSucceeded #2   (i.e. status flips to success via ActionOutcomeObserved)
      |
Refund
      |
Reversal / settlement event
      |
late event arrives
      |
replay from scratch
      |
as_of snapshots
      |
fresh Recovery / Controller / Risk
```

Walking it against the real, current implementation, step by step:

1. `PaymentCreated` -> `PaymentFailed` #1 -> Recovery `RETRY` -> `ActionRequested`
   -> `ActionExecutionStarted` -> `ActionOutcomeObserved(SUCCESS)`: **PROVEN**,
   this exact chain is the attempt-unification checkpoint's own acceptance
   test (`attempt_runner.py` scenario 1), re-run this session.
2. Payment status becomes `success` (`PaymentSucceeded #2` in the diagram
   -- no such literal event type exists or is needed; `ActionOutcomeObserved`
   folded in by `projection.py`'s retry-override logic already *is* this
   fact): **PROVEN**, same evidence.
3. `Refund` against this now-successful, retried payment: **ANALYZED, not
   PROVEN, with a real caveat found.** `RefundRecorded` is a genuinely
   supported, exercised event type (84 real refunds in the backfilled
   dataset). But `backfill.py`'s own refund events set
   `causation_id=payment_terminal_event_id.get(pid)` -- and that dict is
   populated once, from the *original* backfilled terminal event, never
   updated for a live retry (retries are a separate, Stage 3+-only code
   path that has no knowledge of `backfill.py`'s internal bookkeeping,
   and the current dataset never has both a backfilled refund and a live
   retry on the same payment_id, so this was never exercised together).
   A refund issued after a payment resolved via attempt 2 would, under
   today's code, still be recorded with `causation_id` pointing at
   attempt 1's failure -- passes the `CausationOrderViolation` check
   (attempt 1 is still chronologically earliest, so the ordering
   constraint holds), but is semantically imprecise: the refund's *true*
   cause is the successful retry, not the original failure. Not a
   correctness bug in anything proven above; a real ontological loose end
   for whenever Refund and live retries are exercised on the same
   payment.
4. "Reversal / settlement event" (money already paid to a merchant via
   `SettlementReceived`, then clawed back): **UNSUPPORTED.** Confirmed
   directly against `taxonomy.py`'s closed set -- there is no event type
   for this. Attempting to append one would raise `InvalidEventType` at
   the write boundary, exactly the mechanism `TEMPORAL_ONTOLOGY_REVIEW.md`
   already flagged as an untested case (question 10's "reversal after
   settlement," carried forward from that review, still open). This is
   the actual edge of the current model, found honestly rather than
   worked around.
5. "late event arrives", "replay from scratch", "as_of snapshots": **PROVEN**,
   independently, for the parts of the chain that exist -- section A's
   late-event and restart gates, section C's replay-determinism and
   late-arrival-changes-as_of gates. Not proven *chained after step 4*,
   because step 4 has no event to replay in the first place.
6. "fresh Recovery / Controller / Risk" against the resulting world:
   **PROVEN** for Recovery specifically (sections B and D above, twice
   independently); Controller and Risk were not re-run against this exact
   synthetic chain in this review (they operate on Settlement/Device
   subjects, not Payment, and nothing in this chain changes a Settlement
   or Device's state) -- their own behavioral-compatibility gates
   (Stage 1 Gate 2: 607/610 Controller, 26/27 + 0/16 Risk) were re-run
   this session and remain unchanged, confirming they're unaffected by
   everything built in this review, which is the correct, expected
   result given neither one reads Payment.status at all.

**The finding this scenario was built to produce:** the model's edge is
exactly at settlement reversal -- everything before it in the chain is
real and proven; a reversal itself has no representation and would be
rejected outright by the closed taxonomy, not silently mishandled.

## The meta-test

> Given the same valid event history and the same projection cutoff, the
> financial world must be deterministic.

`project(E, T) == project(E, T)` across independent processes/connections:
**PROVEN** (`temporal_adversarial_runner.py` C1, two fully independent
`EventStore` connections and `FinancialStateStore` instances, 1000
payment rows compared, identical).

`project(E, None)` equals the state obtained by incrementally applying
the same valid events: **PROVEN** (Stage 1 Gate 1's original state-
compatibility check, re-run this session, all 7 tables exact).

This is the bridge the user named: everything Phases 1-10 already proved
about Controller/Risk/Recovery's own correctness assumes a single,
trustworthy world snapshot to reason over. This review is the evidence
that the snapshot itself -- whichever connection asks for it, whichever
`as_of` cutoff it asks for -- is the same snapshot every time.

## Summary

**PROVEN:** duplicate/collision rejection (event_id and source-key, both
mechanisms), out-of-order and impossible-timestamp rejection, naive/aware
normalization, restart survival at all three storage layers, cross-
connection and cross-cutoff projection determinism, `as_of`'s "not fixed
until recorded" property, full re-entry (twice), the epistemic boundary
(Policy never reads `investigation_confidence`, Discovery.AI structurally
cannot write state), both directions of the Action boundary, and every
step of the hardest scenario up to (not including) settlement reversal.

**ANALYZED:** the Refund-after-live-retry causation imprecision (a real,
narrow ontological loose end, not a bug in anything currently exercised).

**UNSUPPORTED:** settlement reversal (no event type exists -- structurally
rejected, not mishandled); the Reasoning event layer
(`VerdictProduced`/`PolicyDecided`/etc.) was specified in the taxonomy but
never implemented -- Verdicts/Policy decisions are not currently
event-sourced or `as_of`-able, only Observational + Action facts are;
"exactly one outcome per attempt" remains unenforced at the write
boundary (named already, still deferred).

No new code changes follow from this review by itself -- per the user's
own instruction, the next decision should come from what this exposed,
not be predetermined here.
