# Decision Provenance Adversarial Review

Written per the user's explicit direction, closing the Decision
Provenance checkpoint rather than opening a new implementation phase. The
central attack, stated precisely:

> **Can the system tell the difference between what it decided then and
> what it would decide now?**

Same discipline as every prior review: **PROVEN** (executed this session
against real code, output shown), **ANALYZED** (reasoned from reading the
actual current implementation, not executable through the real pipeline
as built), **UNSUPPORTED** (no legitimate path exists). Backed by
`financial_system/decisions/provenance_adversarial_review.py` (7 new
gates, all PASS) plus `decisions/adversarial_test.py` (4 gates, already
PASS from the implementation checkpoint).

## The fourteen scenarios

| # | Scenario | Status | Evidence |
|---|---|---|---|
| 1 | Historical decision replay | **PROVEN** | `adversarial_test.py` gate 4 -- `world_as_of + logic_version` reproduces the stored `decision`/`decision_score`/`reason` exactly |
| 2 | Policy version change | **PROVEN, mechanism only** | `provenance_adversarial_review.py` PR2/3 -- no real `RULES` edit exists to test against; proves the check itself (`policy_version` string comparison) is sound and would catch a real change if one occurred |
| 3 | Logic version change | **PROVEN, mechanism only** | same test, `logic_version` half |
| 4 | World state changes after a decision | **PROVEN** | PR4 -- the stored `DecisionRecord` (same `decision_id`, same fields) survives the world changing underneath it unedited; a fresh call on the new world honestly diverges (`RETRY` -> `DO_NOT_RETRY`) |
| 5 | Late-arriving event | **PROVEN, and the sharpest result in this review** | PR5 -- see below |
| 6 | Action outcome after decision | **PROVEN by construction** | PR6 -- `DecisionStore` has no method containing "update"; grep-verified, not just asserted |
| 7 | Decision with no action | **UNSUPPORTED (impossible, not merely untested)** | PR7 -- `execute_action_with_events()`'s own source shows `actions.create(action)` on every path before any `return`; `_record_consequential_decision()` only ever runs after that call returns |
| 8 | Duplicate decision attempt | **PROVEN** | PR8/9 -- see below |
| 9 | Same subject, two consequential decisions | **PROVEN** | same test |
| 10 | Restart between `DecisionRecord` and `Action` | **PROVEN, asymmetric** | PR10/11/12 -- see below |
| 11 | Action exists but DecisionRecord doesn't | **PROVEN reachable** | same test |
| 12 | DecisionRecord exists but Action is missing | **PROVEN unreachable, by construction** | same test |
| 13 | Investigation-backed decision | **ANALYZED, currently always absent** | `run_action_loop_v2` calls `run_recovery_for_payment(graph, payment_id, investigate=False)` unconditionally (`action/loop.py`, unchanged since Phase 10) -- every `DecisionRecord` this code can currently produce has `investigation_id=None`. Not a gap in `DecisionRecord` itself (the field exists, and `decisions/adversarial_test.py`'s wiring would populate it correctly if `investigate=True` were ever passed) -- a gap in what the live loop ever asks for. |
| 14 | Deterministic 4A decision | **PROVEN** | Same as scenario 1 -- every decision this checkpoint can produce is 4A-only, since `investigate=False` (scenario 13) |

## Scenario 5, in full: what historical reproducibility actually promises

This is the result the review was built to find, and it does not say what
a casual reading of "replay proven" would suggest. `PR5` takes a real
stored decision (`RETRY`, on a payment whose retry genuinely fails per
ground truth) and, *after* it was recorded, appends one more event: a
legitimate late arrival (`occurred_at` two hours before the decision's
own `world_as_of`, `recorded_at` one hour after it -- itself a valid
event per `TEMPORAL_ADVERSARIAL_REVIEW.md` section A, still `recorded_at
>= occurred_at`). Replaying at the *exact same* `world_as_of`:

```
before the late event was recorded: status='failed'
after the late event was recorded:  status='success'
```

Same cutoff. Different answer. The stored `DecisionRecord` itself never
changes -- `DecisionStore` has no update path (scenario 6) -- but a fresh
replay against that same historical cutoff can now disagree with it. This
is not a flaw in the replay mechanism; it is the honest answer to the
question this whole review exists to ask. The promise
`world_as_of + logic_version + policy_version` actually makes is:

> **same decision, given the same recorded history** --

never "the one true eternal answer for that instant," because "the
history recorded so far" is itself something that grows. This is
`TEMPORAL_ADVERSARIAL_REVIEW.md` section C's own late-arrival finding
(`as_of=T` is not fixed until every event with `occurred_at <= T` has
been recorded), now shown to apply one layer up, to Decisions, not just
to World state -- exactly the connection this review was checking for,
not assuming.

## Scenarios 8/9, in full: decisions are not 1:1 with actions

A payment whose retry genuinely fails stays `failed` -- nothing mutates
it. Calling `run_action_loop_v2` a second time on that same, unchanged
payment reproduces the *identical* verdict, policy decision, and
therefore the identical idempotency key as before. `execute_action_with_events()`
correctly recognizes this and returns the cached result rather than
re-executing (Stage 3 Gate A's own guarantee, holding here too) -- but
`run_action_loop_v2` has no way to distinguish "this call just executed
something new" from "this call replayed a cached result," and records a
`DecisionRecord` either way. Result, verified directly: **one `Action`,
two distinct `decision_id`s, both pointing at it.** This is a real,
now-named property of the current wiring, not a bug this checkpoint
fixes: two independent reasoning acts that happen to agree, and happen to
resolve to one idempotent side effect, is an honest description of what
happened -- `DecisionRecord`'s job is to record *that a consequential
decision was reached*, not to assert exclusive ownership of the `Action`
it authorized. The candidate model in `DECISION_PROVENANCE_SPEC.md`
implied a cleaner 1:1 without saying so; this review is the correction.

## Scenarios 10/11/12, in full: the orphan direction is asymmetric

Because `loop.py`'s call order is fixed (`execute_action_with_events()`
always runs, and always creates+commits its `Action`, before
`_record_consequential_decision()` is ever reached -- verified by
inspecting the actual source, not assumed), a crash between the two
steps can only ever produce one kind of orphan:

- **Action exists, DecisionRecord doesn't** (PR11): reachable, and
  demonstrated directly -- an `Action` was created and committed, then
  the "process" (this test) simply never called the decision-recording
  step, exactly simulating the crash window.
- **DecisionRecord exists, Action doesn't** (PR12): not reachable under
  the current code, by construction, not merely "not observed."

This asymmetry is worth recording as a real property, not smoothed over:
a durable audit trail built from `DecisionStore` today could, honestly,
undercount consequential decisions relative to `ActionStore` (an
`Action` with no matching `DecisionRecord`, from an interrupted process),
but could never overcount them in the other direction.

## What this review deliberately leaves open

Per the user's own framing -- the question was never "how do we pin
everything," it was "where does the promise end":

- **`entity_matches` and reference tables remain unpinned by `world_as_of`**,
  exactly as `DECISION_PROVENANCE_SPEC.md`'s own pre-implementation
  section found. This review did not attempt to close that gap -- Phase 2
  entity resolution is, today, a corpus-level snapshot dependency, not a
  temporal one. Documented, not papered over with fake infrastructure.
- **Investigation-backed decisions** (scenario 13) are specified but
  currently unreachable through the live loop, since `investigate=False`
  is hardcoded there. Not fixed here -- that's a decision about whether
  the live Recovery loop should ever investigate, which is Recovery/4B
  scope, not Decision Provenance scope.
- **Decisions are many-to-one with Actions**, not one-to-one (scenarios
  8/9) -- a real property now named, not something this checkpoint
  changes the wiring to prevent.
- **The orphan direction is asymmetric** (scenarios 10-12) -- named, not
  remediated (no cross-store transaction was introduced; doing so would
  be new infrastructure, not a provenance-model decision).

## Summary

Fourteen scenarios, seven newly proven this session, seven grounded in
work already proven at earlier checkpoints. Nothing failed outright --
every scenario resolved to a **PROVEN**, **ANALYZED**, or (for scenario
7/12) a **structurally impossible, confirmed by reading the actual
call order** result. The one finding worth carrying forward above all
others: historical reproducibility in this system means "same decision,
given the same recorded history, under the same logic and policy
version, with entity resolution assumed unchanged" -- a real,
checkable, honestly-scoped guarantee, and a categorically different
(weaker, more truthful) claim than "the same answer, forever, for that
instant in time."

No further implementation follows from this document. Per the user's own
instruction, the architecture is frozen here for a moment. The next
question is not another temporal feature -- it's whether this foundation
is sufficient for the product this project is actually building toward,
or whether the deliberately-deferred ledger/accounting layer is the next
missing piece. That decision is explicitly not made in this document.
