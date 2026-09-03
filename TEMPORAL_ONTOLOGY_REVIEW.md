# Temporal Ontology Review

Written after Stage 4, at the user's explicit direction: derive this from
the actual experimental evidence Stage 4 produced (the Gate 3 finding
above all), not from fresh speculation. No code changes follow from this
document — it's the checkpoint before deciding whether/how to change the
model, exactly as requested.

## The ten questions

**1. Is `PaymentFailed` an Event, or is it a State?**

An Event — it names a specific, timestamped occurrence ("at time T, we
recorded that this payment failed"). `payments.status = "failed"` is State
— the current, *derived* interpretation of everything known about the
subject. These are related but categorically different, and our own event
naming blurs the line: `PaymentFailed` reads like a state assertion, not a
moment. Worth fixing whenever the taxonomy is revisited — not urgent on its
own, but it's the first thread that unravels into finding #2.

**2. Is `PaymentAttemptFailed` different from `PaymentFailed`?**

Yes, and this is the actual root of the Gate 3 confusion, not a side note.
Our current taxonomy treats "the payment" as having one terminal outcome
(`PaymentFailed`/`PaymentCaptured`, backfilled once in Stage 2) — but Stage
3/4 quietly introduced a *second*, unrelated concept: an "attempt"
(`attempt_number`, tracked only inside `ActionAttempt`/the retry loop,
never connected to the original event). The original payment attempt and
each retry attempt are ontologically **the same kind of fact** — an
attempt's outcome — modeled through two completely different, unconnected
code paths. That's precisely why Recovery's fresh verdict at Gate 3 has no
vocabulary for "this succeeded on a *later* attempt": it was never given a
concept of "attempt" to compare across. `PaymentAttemptFailed{attempt: 1}`
(the original) and `PaymentAttemptSucceeded{attempt: 2}` (the retry) would
be the same taxonomy entry at different attempt numbers, not two unrelated
types.

**3. Is "gateway timeout" an event, an observation, or a property of an event?**

A property of an event — it has no independent timestamp or identity apart
from the failure it explains. `failure_reason` living inside
`PaymentFailed.payload` is the right shape already; nothing to change here.

**4. Can an Observation survive process restart?**

Honestly: there is no "Observation" object to survive anything.
`ONTOLOGY_REVIEW.md` already found this (Observation conflated with
Inference) — `RecoverySignals`/`RiskSignals`/`ReconciliationFact` are
transient function results, recomputed identically from current State
every single call, never persisted. That's not a gap by itself: as long as
State persists (which Stage 1/4 now guarantee) and Finding-computation
stays a pure, cheap function of State, Observation doesn't *need*
independent persistence — it's reproducible on demand. It would need to
change only if Finding-computation ever stopped being cheap and
deterministic (e.g., if it ever involved an LLM call, which by design it
never does).

**5. Does every Finding need to point to the observations that produced it?**

Partially already true, partially not. `ReconciliationFact`/`RiskSignals`/
`RecoverySignals` already carry `evidence`/entity-id lists — pointing to
*which entities* were read. None of them point to *which events*, or *as
of when*, because they're computed straight from current State, not from
the event log directly. That gap only matters once you need to ask "was
this Finding computed before or after event X" — which is exactly
question 7's territory.

**6. Can a Finding become stale when State changes?**

Stage 4's Gate 3 is a Finding going stale in real time, observed directly:
Recovery's verdict for the same payment is different before and after the
outcome event. But "staleness" isn't a *tracked state* in this
architecture — there's no cached Finding sitting around that could go
wrong, because nothing is ever cached. Every call recomputes fresh. This is
a real strength, not an accident: the system is correct-by-freshness
rather than correct-by-invalidation. It only stays true as long as nothing
ever starts caching Findings for performance — the moment that happens,
explicit invalidation becomes necessary and this whole answer changes.

**7. What makes a Finding historical versus currently valid?**

Right now: nothing does, because there's no such thing as a historical
Finding — only historical *events*. But the machinery to get one "for
free" already exists: Stage 1 proved State is fully reconstructible from
the event log by projection. A "historical Finding as of time T" doesn't
need a new persisted object type — it needs a **parameterized projection**
(`project(events, as_of=T)` → State-as-it-was-then), with the *same*,
already-deterministic Finding-computation logic run against that
historical snapshot instead of current State. No new storage, one new
projection parameter.

**8. Can two observations of the same world produce different findings?**

No, currently — and this is worth stating as a validated strength, not
just answering the question. Given identical State, `reconcile_settlement()`/
`compute_recovery_signals()` are fully deterministic, guaranteed by the
four-kinds-of-intelligence boundary (no LLM anywhere in the Finding layer).
The one place non-determinism genuinely could enter is Discovery.AI's own
investigation (temperature, model updates over time) — and it's already
correctly walled off in a *separate* object (`InvestigationResult`), never
inside a Finding. The ontology as built already isolates where
non-determinism is allowed to live from where it must never appear; this
review doesn't need to fix anything here, only confirm it holds.

**9. What exactly causes re-investigation?**

A deterministic pattern match over the event stream: an
`ActionOutcomeObserved` event with `payload.verification_result ==
"FAILURE"`. Already true in the current Phase 10 loop (`_investigate_failure()`
fires under exactly this condition); Stage 4 just made the trigger a real
event instead of an in-memory branch. Nothing new to resolve here — this
question is really asking us to confirm §10 of `MIGRATION_DESIGN.md`'s
answer still holds after real implementation, and it does.

**10. How do we represent temporal validity without turning every object
into an event-sourced blob?**

Don't event-source everything — keep exactly the layering already built:

- **Events**: genuinely event-sourced (append-only, timestamped,
  replayable). Entities and State live here.
- **Findings/Observations**: stay ephemeral, deterministic, recomputed on
  demand. They never need independent temporal-validity tracking, because
  question 7's "project-as-of" capability gives it to them for free,
  without persisting a single extra object.
- **Verdicts/Investigations**: the one layer that *does* get persisted
  (Phase 4's JSONL batches) and *should* carry explicit temporal validity —
  a human or downstream system referencing an old Verdict genuinely needs
  to know whether it's been superseded.

## The synthesis question: multiple temporal snapshots without duplicating the graph

Don't snapshot the graph at all. Keep one event log; make "as-of" a
first-class parameter of the projection layer
(`project(events, as_of=T) -> State`), the same function Stage 1 already
proved correct, just parameterized by time instead of always defaulting to
"now." This is the exact same move Discovery.AI's own unimplemented
View/Projection layer was reaching for — "the same world model explored at
different scopes... without forking into a second graph" — applied to
**time** instead of **relationship family**. Multi-topology-without-forking
and multi-snapshot-without-forking are the same idea, one dimension apart.
Worth naming explicitly: this review didn't invent a new architectural
principle, it found that the one Discovery.AI's own README already claimed
extends cleanly to the one dimension this financial system added that
Discovery.AI never had — time.

## What this review points to, precisely (not implemented)

The concrete fix the evidence converges on: unify "attempt" as a
first-class, ordered property carried on every Payment-subject
Observational/Outcome event — starting at `attempt: 1` for the original
backfilled `PaymentFailed`/`PaymentCaptured`, incrementing for each real
retry's `ActionOutcomeObserved`. That single change would let Recovery's
logic (whenever it's next touched) ask "what was the latest attempt, and
how many prior attempts exist" instead of only "what is the current
status" — which is exactly what would replace Gate 3's confused
`"unrecognized failure_reason=None"` with something that actually says
what happened: this payment succeeded on attempt 2.

Per the standing instruction: this is the destination, not a change made
now. `recovery_agent.py` and the event taxonomy remain untouched until a
deliberate decision is made to revise them.
