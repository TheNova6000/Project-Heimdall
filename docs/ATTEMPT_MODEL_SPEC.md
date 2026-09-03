# Attempt Model Specification

Written per the user's explicit direction after `as_of` projection closed:
a narrow ontology checkpoint before touching any code, answering the
twelve questions and the one critical question, grounded in the real
current implementation (checked directly, not assumed) rather than fresh
speculation. No implementation happens in this document.

## Grounding: what the current code already does

Before answering anything, three facts worth stating because they shape
every answer below:

1. `financial_system/action/loop.py::run_action_loop_v2` already has a
   real, local `attempt_number` variable, starting at 1 and incrementing
   on each observed `FAILURE` that leads to another try
   (`financial_system/action/loop.py:113,137`). It is never written into
   an event payload -- only serialized into the idempotency key string
   (`f"{payment_id}:attempt{attempt_number}:{action}"`,
   `financial_system/action/loop.py:116`) and into the transient,
   never-persisted `ActionAttempt.attempt_number`
   (`financial_system/action/models.py`). Attempt unification is
   therefore not inventing a new number -- it is exposing one that
   already exists in-memory as an explicit, persisted event fact.
2. `Event.payload` is an untyped dict (`financial_system/events/models.py`).
   Adding `attempt_number` to it requires zero schema migration -- no new
   column anywhere, on `events` or on anything else.
3. `recovery/signals.py::compute_recovery_signals` reads
   `payment.properties.get("failure_reason")` and looks it up in
   `FAILURE_TAXONOMY` -- but never reads `payment.properties.get("status")`
   at all (`financial_system/recovery/signals.py:46-50`). `FAILURE_TAXONOMY.get(None)`
   is `None`, so ANY payment with `failure_reason=None` -- including a
   fully successful one, retried or not -- is classified
   `known_category=False` and reasoned about as "unrecognized failure
   reason," never as "nothing to recover." This is the literal mechanism
   behind Stage 4 Gate 3's `INVESTIGATE / unrecognized failure_reason=None`
   result, confirmed directly by reading the two functions together, not
   inferred.

## The twelve questions

**1. What events carry `attempt_number`?**
Every Payment-subject event that represents an attempt or its outcome:
`PaymentCreated`, `PaymentCaptured`, `PaymentFailed` (attempt 1, from
backfill), and `ActionRequested` / `ActionExecutionStarted` /
`ActionOutcomeObserved` (attempt 2+, from the live retry executor).
`OrderCreated`, `SettlementReceived`, `BankTransactionRecorded`,
`RefundRecorded`, `FeeRecorded` never carry it -- they are not
Payment-attempt facts.

**2. Does `PaymentCreated` have `attempt_number=1`, or only outcome events?**
`PaymentCreated` gets `attempt_number=1` too, not just the terminal event.
Reason: attempt 1's *outcome* event already gets `attempt_number=1`
implicitly by being the terminal event backfill.py pairs with
`PaymentCreated` via `causation_id` -- but leaving `PaymentCreated` itself
unlabeled would make attempt 1 the one asymmetric case (inferred from
absence, everything else stated explicitly). Every attempt's start and
outcome carry the same number; no exceptions.

**3. Is `attempt_number` scoped to `payment_id`?**
Yes, always. It has no meaning across payments -- "attempt 2" only means
something relative to one `subject_id`. This is already implicit in how
the idempotency key is built today (`payment_id:attempt{N}:...`) --
formalizing what's already true, not deciding something new.

**4. Can attempt numbers ever be reused?**
No. Monotonically increasing per `payment_id`, starting at 1, never
reused even if a later attempt is somehow rejected before executing
(rejected/blocked attempts still consume a number -- they are a real
attempt at the ontology level even if Policy never authorized execution).

**5. What constitutes starting an attempt?**
Attempt 1 starts at `PaymentCreated`. Attempt N (N>1) starts at
`ActionRequested` -- the moment Policy has proposed a specific retry
action for this payment, which is also already the moment
`event_execution.py` creates a new `Action` row. `ActionExecutionStarted`
is not a new attempt's start; it is a sub-event of the same attempt N
already opened by `ActionRequested` (this is why Stage 4's Gate 1
correctly found neither event mutates state -- they are pre-outcome
phases of one attempt, not new facts about the world).

**6. Does a timeout constitute an attempt outcome?**
Yes, but nothing new needs modeling: "timeout" is already a
`failure_reason` value inside `FAILURE_TAXONOMY`
(`financial_system/recovery/signals.py:24`) and already flows through the
same `PaymentFailed`/`ActionOutcomeObserved(FAILURE)` path as every other
failure category. A timeout is a property of an attempt's outcome, the
same way `TEMPORAL_ONTOLOGY_REVIEW.md` question 3 already settled for
"gateway timeout" generally -- not a fourth event type.

**7. Can an attempt have multiple observed outcomes?**
No -- exactly one terminal fact per attempt (one `PaymentFailed` XOR
`PaymentCaptured` for attempt 1; one `ActionOutcomeObserved` for attempt
N>1). This is not enforced at the write boundary today, and is explicitly
NOT being enforced as part of this checkpoint -- see "What stays
deferred" below. Named here as a should-hold invariant, not implemented
here.

**8. Can an attempt succeed after a previously observed failure?**
No -- that would be two outcomes for the same attempt, which question 7
already rules out. What *can* happen, and is the entire point of this
model, is a **new** attempt (N+1) succeeding after attempt N failed.
Conflating these two is precisely the confusion
`TEMPORAL_ONTOLOGY_REVIEW.md` finding #2 named: today's system has no
way to say "attempt 2 succeeded" as distinct from "the payment
un-failed," because it never numbered the attempts.

**9. How does idempotency interact with `(payment_id, attempt_number)`?**
No change needed -- it already does. `execute_action_with_events`'s
`idempotency_key` already functions as a serialized
`(payment_id, attempt_number, action_type)` composite key today
(`financial_system/action/event_execution.py`'s caller,
`financial_system/action/loop.py:116`); the fix is purely representational
(carry `attempt_number` as its own payload field instead of only inside a
formatted string), not a new mechanism.

**10. How does `as_of` reconstruct the attempt history?**
For free, with zero new code. `as_of` (just proven) already filters
`events.all_events(..., as_of=T)` to `occurred_at <= T`
(`financial_system/events/store.py`). Once `attempt_number` is a payload
field, `events.events_for_subject(payment_id)` filtered the same way
yields the exact, ordered attempt history as it stood at T -- the two
checkpoints compose without either one needing to know about the other.
This is the concrete confirmation that `as_of` and attempt unification
were the right two things to sequence back to back.

**11. What is the canonical current payment status when multiple attempts
exist?**
The status/failure_reason of the *latest* attempt's outcome -- which is
already exactly what `projection.py`'s existing merge logic computes
(terminal event, overridden by the latest qualifying
`ActionOutcomeObserved(SUCCESS, RETRY*)`, ordered by `occurred_at`).
No change needed in `projection.py` for this reason: attempt-number
ordering and occurred_at ordering already agree by construction (attempts
happen in real time order), so "latest occurred_at wins" already equals
"highest attempt_number wins."

**12. Which information remains historical rather than being flattened
into `Payment.status`?**
Everything except the current outcome: the count of attempts, each
attempt's own failure_reason/outcome, and the timing between them.
`Payment` gains **no new column** -- no `attempt_count`,
no `current_attempt_number`. That history lives in, and is only ever
queried from, the event log (`events_for_subject`), exactly the same
principle `as_of` just validated: state is a projection of the latest
fact; history is not flattened into it, it stays queryable at its own
layer.

## The critical question

**Is an attempt a first-class entity, or is it a property of events?**

A property of events. `PaymentAttempt` does not become a new object in
`financial_state`, `financial_graph`, or the event taxonomy's closed set
of types. The taxonomy itself does not grow -- no new event types.
Instead:

```
PaymentFailed { payment_id, attempt_number: 1, failure_reason: ... }
ActionOutcomeObserved { payment_id, attempt_number: 2, verification_result: FAILURE, ... }
ActionOutcomeObserved { payment_id, attempt_number: 3, verification_result: SUCCESS, ... }
```

The reasoning, stated precisely: the only reason `Attempt` was ever
tempting as a first-class object was to give the retry loop a home for
its own bookkeeping, separate from the "real" event stream. But that
bookkeeping (`attempt_number`) already lives inside the loop that
produces exactly the events that should carry it
(`run_action_loop_v2`). Promoting `Attempt` to an entity would mean a
second identity (`attempt_id`) for something that has no independent
existence apart from the events that constitute it -- no attempt is ever
referenced, queried, or reasoned about except through "the Nth event (or
event-pair) for this payment," which a payload field already answers.
This mirrors `ONTOLOGY_REVIEW.md`'s and `TEMPORAL_ONTOLOGY_REVIEW.md`'s
own recurring finding: don't event-source (or entity-source) something
that is reproducible on demand from what's already event-sourced.

## The acceptance test, precisely

The exact shape of Stage 4's Gate 3 confusion becomes the test:

```
Attempt 1 -> FAILURE (technical_failure)
Attempt 2 -> SUCCESS
    |
fresh projection (project(), as_of=None, from the SAME event log)
    |
fresh call to run_recovery_for_payment() -- no special-casing of "this
was a successful retry"; Recovery receives only a Payment node whose
current status is success
    |
expected: NOT "INVESTIGATE / unrecognized failure_reason=None"
expected: a decision that means "nothing to recover here"
```

**The one implementation change this requires, decided now so it isn't
improvised later:** `recovery/signals.py::compute_recovery_signals` must
read `payment.properties.get("status")` (already present on every graph
node -- `signals.py` already reads a sibling payment's `status` at line
64, just never the subject's own) and `recovery_agent.py::_to_verdict`
must check it *before* the `known_category` branch: if the payment's
current status is not `"failed"`, the decision is `DO_NOT_RETRY` /
"payment is not currently failed -- nothing to recover," full stop. This
is a **general** status check, not a retry-specific special case -- it
produces the identical answer whether the payment succeeded on attempt 1,
attempt 2, or attempt 5. That is precisely what proves the ontology
change fixed the actual problem (Recovery had no way to distinguish
"never was a problem" from "unrecognized failure") rather than patching
around one symptom of it.

## What stays deferred

Unchanged from `as_of`'s own report, still parked at the same later
checkpoint (`recorded_at >= occurred_at` enforcement), for the same
reason -- these are event-store write-boundary invariants, not ontology
questions, and conflating them with this checkpoint would blur the two
kinds of work this whole review process has kept separate from the
start:

- Enforcing "exactly one outcome per attempt" (question 7) at write time.
- The timezone-naive/aware mixing finding from the `as_of` report.

Also explicitly out of scope for this checkpoint, per the user's own
framing: no new `Attempt` entity, no `Payment` schema change, no change
to `financial_graph`'s ontology, no change to Discovery.AI, no change to
`run_action_loop`/`run_action_loop_v2`'s control flow (only the payloads
the events they already emit carry).

## Adversarial test scenarios (designed here, run in the implementation step)

1. **Attempt 1 fails, attempt 2 succeeds** -- the acceptance test above.
   Expect: `Payment.status=success`, `events_for_subject` shows
   `attempt_number` 1 then 2, Recovery's fresh verdict is `DO_NOT_RETRY`
   with a status-based reason, not a category-based one.
2. **Attempt 1 fails, attempt 2 also fails (escalation, not resolution)**
   -- expect `attempt_number=2` on the second `ActionOutcomeObserved`,
   `Payment.status` still `failed`, Recovery's fresh verdict still
   reasons from `failure_reason` (category-based path), unchanged from
   today.
3. **Single-attempt payment (no retry ever attempted)** -- expect
   `attempt_number=1` on `PaymentCreated`/terminal event only; `as_of`
   at any T after `PaymentCreated` reconstructs identically to today's
   (pre-unification) behavior -- proves the change is additive, not a
   behavior change for the 913/1000 payments (840 captured + 73 failed
   that were never retried in the real dataset) that never retry.
4. **`as_of` mid-sequence** -- `as_of` set strictly between attempt 1's
   outcome and attempt 2's outcome must reconstruct `attempt_number=1`
   as the only attempt visible, `status=failed` -- literally the same
   Gate 1 `as_of` already proved, now additionally checked to confirm
   `events_for_subject(payment_id)` filtered by the same `as_of` returns
   only the attempt-1 events, not attempt 2's.
5. **Recovery called directly on a payment that was never failed at
   all** (today's Gate 3 payment, status=success from birth, never
   retried) -- expect the SAME `DO_NOT_RETRY` / status-based reason as
   scenario 1, proving the fix is genuinely general and not accidentally
   keyed on the presence of a retry event.
