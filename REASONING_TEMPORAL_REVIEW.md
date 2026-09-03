# Reasoning Temporal Review

Written per the user's explicit direction, immediately after
`TEMPORAL_ADVERSARIAL_REVIEW.md` found that the event-sourced boundary
ends at observed world/action facts, never reaching Reasoning. This
document does not implement anything. It answers the user's thirteen
questions, grounded entirely in the actual current code (every claim
below is a direct read of a real file, not a guess), and resolves the one
critical question the user posed first:

> **Should reasoning events be treated the same way as world events?**

## Grounding: what reasoning artifacts actually exist today

Five kinds of object carry the system's reasoning. Read directly, not
assumed:

| Object | File | `..._id`? | Timestamp? | References evidence? | Persisted? |
|---|---|---|---|---|---|
| `ReconciliationFact` (Controller's Finding) | `reconciliation/deterministic.py` | no | no | `evidence: list[str]` (entity ids) | no -- recomputed every call |
| `RiskSignals` (Risk's Finding) | `risk/signals.py` | no | no | `evidence: list[str]` | no |
| `RecoverySignals` (Recovery's Finding) | `recovery/signals.py` | no | no | `evidence: list[str]` | no |
| `InvestigationRequest`/`InvestigationResult` | `discovery_adapter/models.py` | no (no `investigation_id` field exists anywhere in either model) | no | `evidence: list[str]`, `facts: list[str]` | only via Phase 4's separate JSONL batch (`persistence.py`), and only when that batch tool is explicitly run |
| `AgentVerdict` | `verdict.py` | no (`investigation_id` field just echoes the *subject's* id, e.g. `signals.payment_id` -- not an independent instance identity) | no | `evidence`, `affected_entities` (entity ids) | no |
| `CompoundCase` / `detect_conflicts()` output | `orchestrator/compound_case.py` | no (`subject` is the anchor payment_id, not a case identity) | no | `shared_entities`, `shared_evidence` (entity ids); `investigations: list[str]` is verdicts' subject ids, not real investigation identities | no |
| `Action` (Stage 3+, event-sourced) | `action/models.py` | **yes** -- `action_id` | **yes** -- `created_at`, `execution_started_at`, `execution_completed_at` | `preconditions: dict` -- a flattened *fingerprint* of the verdict that authorized it (`{agent, subject, decision, proposed_action, policy_outcome}`), never the verdict object itself | **yes** -- `ActionStore`, one durable row per action |
| `ActionAttempt`/`ActionCase` (Phase 10, in-memory) | `action/models.py` | no | no (not even an `attempted_at` -- only `attempt_number`, an ordinal, never a clock) | embeds the full `AgentVerdict`/`PolicyDecision` objects directly | no -- `ActionCase` is never written to any store anywhere in the codebase |

Two findings jump out immediately, both confirmed by direct reads, not
inferred:

**1. Every pure-reasoning object in the system is both unidentified and
untimestamped.** Not "under-implemented" -- structurally absent. There is
no `verdict_id`, no `investigation_id` (a real one, distinct from a
subject id), no `finding_id`, no `case_id` for a `CompoundCase`, and no
timestamp field anywhere on any of `ReconciliationFact`, `RiskSignals`,
`RecoverySignals`, `InvestigationResult`, `AgentVerdict`, or `CompoundCase`.
`persistence.py::build_case_record()` -- the one place an investigation
*is* written to durable storage -- confirms this precisely: its output
dict has no timestamp key at all; `case_id` is literally
`settlement_id`, the subject, not an investigation instance. Ordering
across persisted investigation records is JSONL append order, nothing
else.

**2. The only reasoning-adjacent object with real temporal identity is
`Action`, and it carries a fingerprint, not the reasoning itself.**
`Action.action_id` + three real timestamps exist precisely because
`Action` is part of the event-sourced layer `TEMPORAL_ADVERSARIAL_REVIEW.md`
already proved solid. But `Action.preconditions` is a 5-key flattened
dict (`_request_signature()`, `action/event_execution.py`) -- it captures
*that* a particular decision was made, for idempotency-comparison
purposes, not *why* (no `reason`, no `evidence`, no `decision_score`, no
`investigation_confidence`). The full `AgentVerdict` that produced an
`Action` exists only in the caller's Python stack frame at the moment
`execute_action_with_events()` runs, and is gone once that call returns.

## The critical question, resolved

> **Should reasoning events be treated the same way as world events?**

**No.** The grounding above makes the reason concrete, not just
philosophical: world events (`PaymentFailed`, `ActionOutcomeObserved`)
describe something that became true and stays true forever, independent
of who's asking or when they ask -- `TEMPORAL_ADVERSARIAL_REVIEW.md`'s
meta-test proved exactly this determinism. A Finding/Verdict is different
in a way that shows up directly in the code: `_to_verdict()` in
`recovery_agent.py`, `_to_verdict()` in `reconciliation/controller.py`,
and `risk_agent.py`'s scoring function are all **pure functions of
current graph state**, recomputed identically on every call
(`TEMPORAL_ONTOLOGY_REVIEW.md` question 8, re-confirmed true throughout
this entire migration). A world event has exactly one occurrence time. A
Verdict has at minimum *two* meaningfully different times -- when the
world state it reasoned over existed, and when the reasoning itself ran
-- and those can diverge arbitrarily (the same payment, same graph state,
reasoned about a week apart, produces the identical verdict; the same
payment reasoned about before and after a retry event produces different
verdicts on the identical wall-clock day). Treating a Verdict as "just
another event with an `occurred_at`" would collapse a distinction the
current architecture keeps correctly separate elsewhere: `decision_score`
(always fresh, always recomputed, never a stored fact to trust) versus
`investigation_confidence` (Discovery.AI's own, explicitly audit-only,
per `policy/rules.py`'s own docstring). Event-sourcing Reasoning naively
would risk exactly the mistake Policy already refuses to make with
`investigation_confidence` -- treating a *record of a past belief* as if
it were a *world fact* a later decision could authorize itself against.

## The six clocks

The user's own framing, checked against what the code actually
distinguishes today:

```
WORLD TIME         -- Event.occurred_at (real, enforced, TEMPORAL_ADVERSARIAL_REVIEW.md section A)
OBSERVATION TIME    -- does not exist as a distinct concept; Findings are computed
                        synchronously with whatever calls them, no separate "observed at"
INVESTIGATION TIME  -- exists only implicitly: llm_latency_seconds (call_metrics.py) measures
                        DURATION, not a timestamp; no investigation has a recorded start/end instant
VERDICT TIME        -- does not exist; AgentVerdict has no timestamp field, confirmed above
POLICY TIME         -- does not exist; PolicyDecision (policy/engine.py) has no timestamp either
                        (checked directly: same pattern as AgentVerdict)
ACTION TIME         -- real, and the ONLY one of the six actually implemented:
                        Action.created_at / execution_started_at / execution_completed_at
```

One clock genuinely exists among the five reasoning-adjacent ones the
user named: Action time. The other four are not weakly implemented --
they are entirely absent as concepts in the running code. This matters
for answering question 9 precisely below: `as_of` cannot mean anything
for Investigation/Verdict/Policy time today because nothing marks when
any of those actually happened.

## The thirteen questions

**1. What reasoning artifacts currently exist?**
`ReconciliationFact`, `RiskSignals`, `RecoverySignals` (Findings --
Controller/Risk/Recovery's own deterministic signal computations);
`InvestigationRequest`/`InvestigationResult` (Discovery.AI's contract);
`AgentVerdict` (the common decision object all three domain agents
produce); `PolicyDecision` (`policy/engine.py`); `CompoundCase` +
`detect_conflicts()`'s output (Phase 8's cross-domain merge). Full
inventory in the grounding table above.

**2. Which are ephemeral?**
All of them except `Action`. Every Finding, `InvestigationResult` (unless
separately routed through Phase 4's JSONL batch tool -- not part of the
live decision pipeline), `AgentVerdict`, `PolicyDecision`, and
`CompoundCase` live only in a Python call stack and are discarded when
the call returns. This was already named as a deliberate strength in
`TEMPORAL_ONTOLOGY_REVIEW.md` question 6 ("correct-by-freshness rather
than correct-by-invalidation") -- this review confirms it still holds,
uniformly, across every reasoning object, not just Findings.

**3. Which have IDs?**
Only `Action` (`action_id`, real UUID, `action/event_execution.py`).
Nothing else -- see the grounding table's `..._id?` column. Where an
"id-shaped" field exists (`AgentVerdict.investigation_id`,
`CompoundCase.investigations`), it is always the *subject's* id
(a `payment_id` or `settlement_id`), never an independently-generated
instance identity. Two investigations of the same payment on different
days would be indistinguishable by id, because there is no id.

**4. Which have timestamps?**
Only `Action`. Confirmed by direct read of every dataclass/pydantic model
listed in the grounding table -- none of the others declare a datetime
field.

**5. Which reference observations?**
Every Finding and `AgentVerdict` carries `evidence: list[str]` --
but these are graph **entity ids** (payments, settlements, devices),
never event ids and never an `as_of` cutoff. This is exactly
`TEMPORAL_ONTOLOGY_REVIEW.md` question 5's finding, re-confirmed
unchanged: a Finding points to *which entities* it read, never *which
version of them, at what time*. Given entities are themselves only
projections of the event log (proven throughout this migration), this
means today's evidence trail is one layer removed from the actual facts
that produced it -- traceable to "the payment," not to "the specific
`PaymentFailed`/`ActionOutcomeObserved` event(s) that made the payment's
state what it was when this Finding read it."

**6. Can a verdict be reproduced?**
Yes, deterministically, for the 4A/deterministic-signal portion --
proven throughout this entire migration (Stage 1 Gate 2's 607/610,
26/27+0/16, 87/87, all re-verified this session). Not for the 4B/LLM
portion when `investigate=True` -- Discovery.AI's narrative and
`investigation_confidence` are not guaranteed reproducible across calls
(model updates, temperature), and the architecture already, correctly,
never lets that non-reproducible part touch `decision`/`decision_score`
(`TEMPORAL_ONTOLOGY_REVIEW.md` question 8). Reproducibility of a Verdict
is therefore not one property but two, cleanly split at the same
boundary Policy already respects.

**7. Can a verdict become stale?**
Yes, demonstrated directly and repeatedly: Stage 4 Gate 3's original
finding, and `temporal_adversarial_runner.py` B2's fresh second call both
showed the identical payment producing a different Recovery verdict
before and after an `ActionOutcomeObserved` event. Staleness here is not
a tracked *state* -- nothing marks an old verdict "stale" -- it is simply
that nothing is ever kept around long enough to *become* stale in the
first place. That is a real answer, not a dodge: staleness as a tracked
property only matters for something cached, and nothing is cached.

**8. What is `as_of` for reasoning, today?**
Nothing is stored, so `as_of` cannot filter a persisted Verdict history
that doesn't exist. But something adjacent and genuinely useful already
works, worth stating precisely because it's easy to conflate with the
thing that doesn't exist: `project(events, as_of=T)` (proven,
`asof_runner.py`) plus a fresh call to `run_recovery_for_payment()`/
`run_controller_for_settlement()`/`run_risk_for_device()` against the
graph built from that snapshot already answers **"what would today's
reasoning logic conclude about the world as it stood at T"** --
`temporal_adversarial_runner.py`'s own scenario 4 and `attempt_runner.py`'s
scenario 4 do exactly this, today, with zero new code. What this does
**not** answer, and cannot, even in principle, is **"what did the system
actually conclude, and tell a human or act on, at the time"** -- because
Recovery's own logic (the `FAILURE_TAXONOMY` table, the rule set, even
the status-check branch added this checkpoint) is itself something that
changes over calendar time, and re-running *today's* logic against
*yesterday's* world state is not the same claim as *recovering what
yesterday's logic said*. These are two different questions this review
is naming as genuinely distinct for the first time:

- **Recomputed historical belief** -- current logic, past world. Answerable today, via `as_of` + a fresh agent call.
- **Recorded historical belief** -- the logic version that actually ran, at the time it ran, against the world as it then stood. Not answerable today, for any Verdict, because nothing about a Verdict's own production is durable, versioned, or timestamped.

**9. Should investigations be replayable?**
Not in the sense of re-running the exact same LLM call and expecting the
exact same narrative -- that would fight the non-determinism the
architecture already correctly isolates (question 6 above). What *is*
worth being replayable, and currently isn't, is the deterministic 4A
half: `expected_amount`/`actual_amount`/`unexplained_amount`/`facts` are
pure functions of graph state (`reconciliation/deterministic.py`), so
replaying 4A against an `as_of` snapshot is exactly as sound as replaying
a Finding, and for the same reason. Replayability of an investigation is
therefore not one question either -- it's the same 4A/4B split as
question 6, asked from a different angle.

**10. Should policy decisions be immutable?**
`PolicyDecision` objects already behave as if they were -- nothing in
`policy/engine.py` ever mutates one after `evaluate()` returns, and
`Action.preconditions` (the one place a decision's fingerprint survives)
is compared, never overwritten, by the idempotency check in
`event_execution.py`. The real question this exposes is not mutability
but existence: a `PolicyDecision` is already immutable *while it exists*,
it simply doesn't exist for longer than one function call. Immutability
was never the gap; durability was.

**11. What is the canonical current payment status when multiple
attempts exist?** *(carried over from `ATTEMPT_MODEL_SPEC.md`, re-asked
here for reasoning rather than world state)* -- there is no equivalent
concept for Verdicts, because there is no persisted verdict history to
have a "canonical current" member of. The closest real analogue,
`ActionCase.case_status`, is computed fresh at the end of
`run_action_loop`/`run_action_loop_v2`'s own loop, from that loop's own
in-memory `attempts` list -- never derived from a durable Verdict
sequence, because none exists.

**12. What happens when a late financial event invalidates an earlier
verdict?**
Nothing needs to happen, today, and that's the honest answer rather than
a gap: because no verdict is ever stored, there is no earlier verdict
sitting somewhere claiming to still be true that a late event could
contradict. The very next call to the same agent function simply
recomputes against whatever state exists then, late event included --
`temporal_adversarial_runner.py`'s own late-event finding (section G of
`TEMPORAL_ADVERSARIAL_REVIEW.md`) proves this exact mechanism for World
state, and Findings/Verdicts inherit it for free by virtue of always
being recomputed rather than cached. The moment any reasoning artifact
*does* become durable, this question turns real and hard -- a stored
`VerdictProduced` event, once it exists, has exactly the same "not fixed
until superseded" problem the late-event finding already demonstrated
for World state, except now there's a second artifact (the stored
verdict) that could actively mislead a reader who doesn't know it's
stale, which a purely-recomputed Finding structurally cannot do.

**13. What does "what did the system know then?" mean?**
This review's central finding, and the reason question 8's split matters
more than any single missing field: "what did the system know then" is
ambiguous across exactly the two readings question 8 separated --
*recomputed* ("what would we conclude now, about then") versus
*recorded* ("what got concluded and acted on, back then"). The current
architecture answers the first honestly and well, and cannot answer the
second at all, for any payment, ever, retroactively -- not because of a
missing field, but because nothing about a past reasoning act was ever
captured. That is the actual shape of the boundary
`TEMPORAL_ADVERSARIAL_REVIEW.md` found: not "reasoning events are
missing from the taxonomy," but "the question this review was asked to
answer doesn't yet have a durable substrate to be answered from."

## Synthesis: what this means for "should we event-source Reasoning"

Not a yes/no verdict -- the user was explicit that this document
shouldn't manufacture one -- but the grounding above sharpens the actual
decision considerably narrower than "add `VerdictProduced` to the
taxonomy":

- **World events and Action events** are event-sourceable exactly as
  built, because they describe things that are true independent of who's
  asking (`TEMPORAL_ADVERSARIAL_REVIEW.md`'s determinism meta-test is the
  proof).
- **A naive `VerdictProduced` event** (a Verdict, stamped with an
  `occurred_at`) would conflate "when the world state existed" with "when
  the reasoning ran" -- exactly the two-clock problem this review found
  the code has no way to distinguish today, and exactly the kind of
  conflation Policy's own `investigation_confidence` boundary already
  shows this codebase knows how to avoid when it's paying attention.
- **What a Verdict-as-fact-record would need**, if built deliberately
  rather than by analogy to World events, is at minimum two timestamps,
  not one -- something like "world state observed as of `T_world`" and
  "conclusion reached at `T_reasoning`" -- plus, per question 8, an
  explicit marker of *which version of the reasoning logic itself*
  produced it, since that's the piece "recomputed" can never recover and
  "recorded" is the only thing that could.
- **The 4A/4B split already in the codebase** (deterministic reconciliation
  arithmetic vs. LLM narrative) is very likely the natural fault line for
  *what* gets recorded, if anything does: 4A is exactly as reproducible
  and event-sourceable as World state; 4B's narrative is not, and
  recording it as a fact-with-a-timestamp would misrepresent something
  that was never a fact about the world to begin with -- it's a fact
  about what one LLM call, on one day, with one prompt, said.

No implementation follows from this document. Per the user's own
sequencing, the next decision -- whether to event-source Reasoning at
all, and if so, only the 4A/deterministic half or the full Verdict --
should be made deliberately, from this grounding, not predetermined by
having written it.
