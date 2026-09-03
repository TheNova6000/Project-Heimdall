# Decision Provenance Specification

Written per the user's explicit direction, replacing "Reasoning Event
Sourcing" as the framing entirely. `REASONING_TEMPORAL_REVIEW.md` found
that every pure-reasoning object is deliberately ephemeral and that only
`Action` has real temporal identity. This document does not decide to
event-source Reasoning -- it asks a narrower question, grounded in the
same code:

> **What minimum durable information must be recorded so that a past
> consequential decision can be explained without pretending that every
> intermediate thought was a historical fact?**

No implementation follows from this document. It answers the fourteen
questions (the user's thirteen plus the Discovery.AI question), proposes
a candidate model, and adversarially reasons through it -- against the
real, current code wherever a real code path exists to reason against,
marked honestly where it doesn't.

## One more grounding fact, found while answering question 1

`REASONING_TEMPORAL_REVIEW.md` already established that `Action` is the
only reasoning-adjacent object with real identity and timestamps. Reading
`orchestrator/orchestrator.py` and `policy/runner.py` together surfaces a
sharper, previously unstated fact: **"consequential" is not currently a
property of a Verdict or even a Policy outcome -- it's a property of
whether anything is wired to call an executor at all.**

`orchestrator.py::process_payment()` runs Controller/Risk/Recovery and
merges their verdicts into a `CompoundCase` -- and stops there. It never
calls `policy.evaluate()`. `policy/runner.py::run_full_corpus_check()`
does call `evaluate()` on all three verdict slots when present, across
all 1000 payments -- but purely as a scoring/done-check harness for
Phase 9, and its own printed output (`Outcomes: {'REVIEW': 57, 'ALLOW':
87, 'ESCALATE': 16}`, `Rules fired:` naming only the three Recovery rules
R3/R4/R9) shows every outcome in that run resolving through a Recovery
verdict -- worth a closer look before relying on it further (not pursued
here, out of scope for this document), but not needed to establish the
point that matters: regardless of what that harness computes, it only
*scores* Policy outcomes, it never calls an executor. The only real, live
path from a Verdict to an `Action` is
`action/loop.py::run_action_loop_v2`, which calls Recovery directly
(`run_recovery_for_payment`), never through the orchestrator, and never
for Controller or Risk. So today: a Risk verdict of `HOLD` -- however
clearly it would map to Policy's `BLOCK` -- never produces an `Action`,
a `Action`-adjacent event, or any durable trace, because nothing ever
calls the executor for it. Consequentiality, right now, is entirely an
accident of which agent's output happens to be wired to
`action/loop.py`, not a property the architecture assigns deliberately.
This is the first concrete thing Decision Provenance needs to fix
regardless of what else it does: **consequentiality should be a property
of the decision, not of which pipeline happened to call it.**

## The fourteen questions

**1. What makes a reasoning act consequential?**
Refined from the grounding above, precisely: a reasoning act is
consequential when it results in (or, honestly, *would* result in, once
the wiring gap above is closed) a `PolicyDecision` whose `outcome`
authorizes a real-world side effect -- today that means `outcome ==
"ALLOW"` reaching `execute_action_with_events()`. Everything upstream of
that point (Findings, the Verdict itself, even a `BLOCK`/`ESCALATE`/
`REVIEW` outcome that authorizes nothing) is reasoning *about* the world,
not an act *on* it. This mirrors, at the Reasoning layer, exactly the
distinction `taxonomy.py` already draws between `STATE_PROJECTING_TYPES`
(`OBSERVATIONAL | {ActionOutcomeObserved}`) and everything else -- only
the events that actually change the world get to be authoritative;
everything else is context.

**2. Which decisions must be historically reconstructable?**
Only consequential ones, per question 1. A Risk verdict that never
authorized anything doesn't need a historical record any more than a
Finding does -- `REASONING_TEMPORAL_REVIEW.md` question 2 already
established Findings are fine staying ephemeral. The dividing line is
not "which agent" (Controller vs. Risk vs. Recovery) -- it's "did Policy
authorize an action from it."

**3. Which intermediate reasoning objects can remain ephemeral?**
`ReconciliationFact`, `RiskSignals`, `RecoverySignals` (all three
Findings) -- always, regardless of consequentiality, because they're
already proven reproducible from `(event history, as_of cutoff, code
version)` (`REASONING_TEMPORAL_REVIEW.md` question 6's 4A half). A
`PolicyDecision` that resulted in `BLOCK`/`ESCALATE`/`REVIEW` (no action
follows) can also stay ephemeral -- nothing durable needs to explain a
decision that changed nothing. The only objects this spec is proposing
to stop treating as ephemeral are the Verdict and PolicyDecision *that
led to an Action*, and the reference to whatever Investigation informed
them.

**4. What exactly must be recorded for a historical Verdict?**
Not the whole `AgentVerdict` object verbatim -- per the critical finding
below (question 12), a full copy invites exactly the "same decision?"
confusion this spec exists to avoid. Minimum: `decision`, `decision_score`,
`proposed_action`, `reason`, `evidence` (already all present on
`AgentVerdict`, just never persisted past the call), plus two things that
don't exist on it today: a `logic_version` (see question 9) and an
explicit reference to the world snapshot it reasoned over (a `world_as_of`
timestamp -- the missing "observation time" clock
`REASONING_TEMPORAL_REVIEW.md` found absent). `investigation_confidence`
travels with the Verdict already and should keep traveling with its
historical record too, still explicitly audit-only, per the same
boundary Policy already enforces.

**5. What exactly must be recorded for `PolicyDecision`?**
`outcome`, `rule_id`, `rule_description` (already present -- `rule_id`
alone is not enough on its own once question 9's version question is
taken seriously: the same `rule_id` string could mean a different rule
after `policy/rules.py` is edited), plus a `policy_version` alongside the
Verdict's `logic_version`. `PolicyDecision` deliberately has no
`investigation_confidence` field today (`policy/engine.py:27`'s own
comment explains why) -- a historical record must preserve that omission,
not "fix" it by adding the field back in under a provenance banner.

**6. Does an investigation need durable identity?**
Yes, but narrower than a full record: a stable `investigation_id` (which,
per the grounding table in `REASONING_TEMPORAL_REVIEW.md`, doesn't
currently exist anywhere -- `AgentVerdict.investigation_id` just echoes
the subject id) that a consequential Decision can *reference*. The
investigation's own full content (narrative, hypotheses, evidence) does
not need to live inside the Decision record -- see question 13's answer
below, and the added Discovery.AI question.

**7. How are deterministic 4A results represented?**
Not persisted at all, as their own object -- referenced instead, by
`(event_ids or as_of cutoff)` plus `logic_version`, exactly per
`REASONING_TEMPORAL_REVIEW.md` question 9's answer: 4A is reproducible on
demand from `(event history, as_of, code version)`, so persisting it
would be redundant with the event log this whole migration already
proved trustworthy. A historical Decision's `reasoning_basis` needs
enough to *recompute* the Finding, not the Finding's own value frozen in
amber (which could drift out of sync with a reproducible source of
truth, the exact anti-pattern `TEMPORAL_ONTOLOGY_REVIEW.md` question 6
already warned against for caching).

**8. How are 4B Discovery results referenced?**
By `investigation_id` (question 6) plus enough of a fingerprint to know
*which* narrative/confidence pair was read at decision time --
`narrative` and `investigation_confidence` are not reproducible
(question 6 of `REASONING_TEMPORAL_REVIEW.md`), so unlike 4A, a 4B
reference genuinely needs the *content*, not just a recomputation
pointer, to be durable. Practically: this is exactly what Phase 4's
existing `persistence.py::build_case_record()` already writes to JSONL
-- it just isn't currently referenced *from* anything, and has no id or
timestamp of its own (both real, confirmed gaps, not design choices).

**9. What logic/version information is required?**
This is the question the user's own message correctly identified as the
missing third dimension, and it's real: `FAILURE_TAXONOMY`
(`recovery/signals.py`) and `RULES` (`policy/rules.py`) are both plain
Python module-level data today -- no version number, no changelog, no
way to know which revision produced a given historical verdict. Minimum
viable answer, deliberately cheap rather than a full versioning system:
a single string constant per module (`RECOVERY_LOGIC_VERSION`,
`POLICY_RULES_VERSION`), bumped by hand whenever `FAILURE_TAXONOMY`/
`RULES` changes, recorded alongside a historical Decision. Not proposing
git-commit-hash-level provenance (out of scope, and this project has no
git repository to hash against, per this environment's own setup) --
just enough that "same decision across versions" (question 12) has an
actual answer instead of a silent assumption.

**10. What happens when a late event invalidates an earlier decision?**
Nothing automatic, deliberately -- mirroring `REASONING_TEMPORAL_REVIEW.md`
question 12's answer, extended: a Decision record, once written, is a
historical fact about *what was decided*, not a live claim about
*what's still true*. A late event changing the world doesn't retroactively
edit a Decision any more than it retroactively edits a `PaymentFailed`
event -- it produces new events, which a *new* reasoning act (and, if
consequential, a new Decision) responds to. The old Decision stays
exactly as historically accurate as it always was: "given the world as
observed at `world_as_of`, under `logic_version`, this is what was
decided." This is precisely why `world_as_of` (question 4) has to be its
own field, distinct from `created_at` -- a late event can only ever be
visible to a Decision made *after* it arrives, never retroactively to
one made before, which is `TEMPORAL_ADVERSARIAL_REVIEW.md` section C's
own late-event finding, carried up one layer.

**11. Can a historical decision be replayed versus merely inspected?**
Split, same as `REASONING_TEMPORAL_REVIEW.md` question 9 found for
investigations: the 4A/deterministic portion of a historical Decision
*can* be replayed -- rebuild the world via `project(events,
as_of=world_as_of)`, re-run the Finding computation under
`logic_version`, and it should reproduce identically (this is a real,
testable claim, not a hope -- it follows directly from the determinism
already proven throughout this migration). The 4B/investigation portion
can only ever be *inspected* -- re-running Discovery.AI is a new
investigation, not a replay of the old one, exactly per
`REASONING_TEMPORAL_REVIEW.md` question 6. A Decision record's
`reasoning_basis` should therefore make clear which of its parts are
replayable evidence and which are inspectable-only citations -- this is
the single most important structural distinction the candidate model
below is built around.

**12. What does "same decision" mean across software/policy versions?**
The critical question, and the reason `logic_version`/`policy_version`
aren't optional metadata but the actual point of this whole spec: without
them, "would this decision be the same today" is unanswerable except by
accident. With them: "same decision" means `(world_as_of, logic_version,
policy_version)` all match and the 4A recomputation (question 11)
produces the identical Finding -- at which point the historical Verdict
and a freshly recomputed one are provably the same claim, not just
similar-looking ones. Without a version match, a historical Decision and
a fresh recomputation are two different questions wearing the same
shape, and conflating them is exactly the mistake
`REASONING_TEMPORAL_REVIEW.md` question 8 named (recomputed vs. recorded
historical belief) -- version tracking is what makes that distinction
checkable in code instead of only arguable in prose.

**13. How does the existing `Action` provenance fit into the model?**
It's the anchor, not a separate concern. `Action.preconditions`
(`_request_signature()`) already carries `{agent, subject, decision,
proposed_action, policy_outcome}` -- a fingerprint of exactly the fields
question 4/5 propose making durable. The candidate model below doesn't
compete with `Action` -- it fills in the one thing `Action` was never
designed to carry: the *reasoning* (`reason`, `evidence`,
`investigation_id`, `logic_version`) behind the fingerprint it already
stores. Concretely: a `Decision` record and its `Action` would share the
same `case_id`/`correlation_id`, exactly the linkage
`event_execution.py` already establishes between an `Action` and its
events -- Decision Provenance extends that existing correlation
backwards one more hop, from "the action that ran" to "the reasoning
that authorized it," rather than inventing a new linkage mechanism.

**14 (added, Discovery.AI-specific). Does investigation provenance need
to be durable independently of the financial decision, or is a reference
from the consequential decision sufficient?**
A reference is sufficient, and independence would be a mistake, for a
reason grounded directly in `discovery_adapter`'s own structure: an
investigation is only ever opened *in service of* a specific Controller/
Risk/Recovery call (`investigate_evidence()` is invoked from inside
`run_controller_for_settlement()`/`run_risk_for_device()`/
`run_recovery_for_payment()`, never standalone) -- it has no independent
reason to exist, and `REASONING_TEMPORAL_REVIEW.md`'s grounding already
confirmed Discovery.AI cannot write to financial state even if it wanted
independent standing. Making investigation provenance durable
*independently* would invite exactly the confusion this whole spec is
trying to avoid: a free-floating `InvestigationResult` with no
consequential decision attached would look like a historical fact with
nothing to explain, dangerously close to the "every intermediate thought
becomes world history" outcome explicitly rejected at the top of this
document. A reference from the Decision that used it -- durable only
when the Decision itself is durable -- is the correct, narrower answer.

## Candidate model (not implemented)

```
Decision
├── decision_id            -- new; nothing today has this
├── case_id                -- == Action.case_id, when one exists (question 13)
├── subject
├── agent                  -- "controller" | "risk" | "recovery"
├── decision                -- e.g. RETRY / BLOCK / DO_NOT_RETRY
├── decision_score
├── reason
├── evidence                -- entity ids, same shape as AgentVerdict.evidence today
├── policy_outcome          -- ALLOW | BLOCK | ESCALATE | REVIEW
├── policy_rule_id
├── reasoning_basis
│    ├── world_as_of         -- the as_of cutoff the Finding/Verdict reasoned over (question 4/10)
│    ├── logic_version        -- which FAILURE_TAXONOMY/reconciliation logic (question 9)
│    ├── policy_version       -- which RULES (question 9)
│    └── investigation_id     -- optional; reference only, per question 14
├── created_at               -- when the Decision itself was produced (question 4's second clock)
└── action_id                -- optional; set only when policy_outcome == ALLOW and an Action followed
```

Deliberately absent: no `investigation_confidence` field (mirrors
`PolicyDecision`'s own deliberate omission, question 5); no embedded
`InvestigationResult` (question 14); no field for a Finding's own raw
values (question 7 -- those are recomputed, not stored).

## Adversarial reasoning against the candidate model

No code exists yet, so nothing here is **PROVEN** in the sense the prior
three review documents used that word. Each scenario below is reasoned
against the *actual current* code it would sit on top of (cited
directly), marked **ANALYZED** where an existing code path makes the
reasoning checkable, and **OPEN** where the model itself would need to
decide something this document hasn't settled.

1. **Two Decisions, same subject, same `world_as_of`, different
   `logic_version`.** Should be allowed to disagree -- that's precisely
   what `logic_version` existing is for (question 12). **ANALYZED**:
   `FAILURE_TAXONOMY`'s `technical_failure` base rate (0.85) could
   plausibly be tuned after more data; two Decisions straddling that
   change, same world, different `decision_score`, is the model working
   as intended, not a conflict to resolve.
2. **A Decision references an `investigation_id` whose underlying
   `InvestigationResult` was never persisted** (today's live pipeline,
   `investigate=True` without the separate JSONL batch tool running).
   **OPEN**: the model as sketched assumes question 14's reference is
   always resolvable; today it frequently wouldn't be, since
   `persistence.py` is a separate, manually-invoked path from the live
   `investigate_evidence()` call. This spec would need to either make
   persisting the referenced investigation mandatory whenever a Decision
   is durable, or accept dangling references as a known, honest
   limitation, the same way `evidence: list[str]` today can reference an
   entity without pinning which version of it.
3. **A late event arrives with `occurred_at` before an existing
   Decision's `world_as_of`.** Per question 10, the old Decision is
   untouched. **ANALYZED**, directly from `temporal_adversarial_runner.py`
   section G's already-proven mechanism: a fresh `as_of` query at the
   same cutoff would now see the late event and could produce a
   *different* recomputed Finding than the stored Decision's own
   `decision_score` -- which is exactly the "recomputed vs. recorded"
   split (question 8 of `REASONING_TEMPORAL_REVIEW.md`) working as
   designed, not a contradiction: the stored Decision remains an accurate
   record of what was decided at `created_at`; a fresh recomputation
   would now honestly reflect more complete information.
4. **Replaying the 4A portion of an old Decision produces a different
   Finding than what's stored, even with matching `logic_version` and
   `world_as_of`.** **OPEN, and important**: this should never happen if
   `logic_version`/`world_as_of` genuinely capture everything
   deterministic about the computation -- if it does happen, it means
   something the model assumed was pinned (a hidden dependency on
   ambient state, e.g. `datetime.now()` used somewhere inside a
   "deterministic" Finding function) actually isn't. This spec doesn't
   currently require proving `logic_version` is a *complete* pin, only
   that one exists -- a real gap the adversarial-test-once-implemented
   step would need to close, analogous to how `test_recorded_before_occurred_gap`
   started as a named gap and only became a real gate once implemented.
5. **A Decision authorized an `Action` that was later idempotently
   replayed** (`event_execution.py`'s cached-result path, already proven
   in Stage 3 Gate A). **ANALYZED**: the replay reuses the *same*
   `Action`, never creates a second one -- the Decision that originally
   authorized it stays the single authorizing record; a second
   `execute_action_with_events()` call with the same idempotency key
   should not, and under this model would not, produce a second
   `Decision` row, since no new reasoning act actually occurred.
6. **Risk proposes `HOLD` (today, never wired to an `Action` at all --
   see the grounding finding above).** **OPEN**: under question 1's
   definition, this Decision would not be durable today, because nothing
   calls an executor for it -- exactly the wiring gap this document
   named as the first thing to fix. Closing that gap is a precondition
   for this spec fully applying to Controller/Risk, not something the
   spec itself resolves.

## Resolving `logic_version` completeness, before implementing anything

Per the user's explicit instruction: don't guess what belongs in
`logic_version` -- inspect the actual deterministic dependency graph
behind a real 4A decision and check whether `world_as_of + logic_version
+ policy_version` genuinely pins it. Traced directly through
`recovery_agent.py::run_recovery_for_payment()` (the only agent this
checkpoint will wire up, per the user's own scoping below), a Recovery
Verdict depends on:

1. **Event history, filtered by `world_as_of`** -- via `project()`.
   Pinned, correctly, by `world_as_of`. Proven throughout this migration.
2. **Reference tables** (merchants/customers/devices/instruments) --
   `backfill.py`'s own documented scope decision: these are standing
   entities, never event-sourced, always read as their *current* row
   regardless of any `as_of` cutoff. **Not pinned by `world_as_of` --
   structurally has no history to pin.** Named already in `backfill.py`'s
   own docstring as a deliberate simplification; this review is the
   first place it's connected to what it means for replay.
3. **`entity_matches`** (Phase 2's persisted matching output, e.g. the
   `belongs_to` edges `compute_recovery_signals()` walks to find sibling
   payments on the same order) -- and here is the real, previously
   unstated finding: **checked directly against every runner this
   migration has written** (`asof_runner.py`, `attempt_runner.py`,
   `temporal_adversarial_runner.py` -- grep confirms `run_phase2()` is
   called exactly once per runner, always against the full,
   direct-ingestion `STATE_DB`, **never** against an `as_of`-filtered
   snapshot), entity matching is never re-run per cutoff. It is computed
   once, from whatever the *current* full financial state is, and every
   graph -- whether built for "now" or for a historical `as_of` snapshot
   -- reads the same, single, current `entity_matches` table.
   **`world_as_of` therefore does NOT pin `entity_matches` -- a graph
   built "as of last month" would still see this month's entity
   resolution result.**
4. **`FAILURE_TAXONOMY` + the `_to_verdict()`/`compute_recovery_signals()`
   function bodies** -- code-level, exactly what `logic_version` (below)
   is meant to pin.
5. **`GraphRepository`/`build_graph()`'s own construction** -- code-level
   (also under `logic_version`), with one narrow caveat worth naming
   honestly rather than hiding: `FinancialStateStore.all_rows()` has no
   explicit `ORDER BY`, so row order is whatever SQLite's own storage
   order happens to be -- stable in practice for a fixed sqlite build and
   an insert-only table, but not a *guaranteed* invariant the way
   `occurred_at`-ordering is for events.

**Conclusion: `world_as_of + logic_version + policy_version` is
insufficient as originally specified.** It correctly pins the
event-sourced and code-level inputs, but silently assumes reference
tables and `entity_matches` are either irrelevant or themselves
time-invariant -- neither is quite true. The honest fix, scoped to what
this checkpoint is actually implementing (see below): document the gap
explicitly rather than papering over it with a field that would imply a
guarantee the system doesn't provide. A `DecisionRecord`'s `world_as_of`
should be understood, precisely, as: *"the event-sourced financial state
was frozen at this cutoff; reference data and entity resolution were
whatever they currently are at read time, not independently pinned."*
Closing this gap for real (event-sourcing or otherwise time-scoping
`entity_matches`) is out of scope for this checkpoint and not proposed
here -- named as a real, open limitation of `world_as_of`, not solved by
inventing a second version field to paper over it.

One practical consequence follows directly: this checkpoint's own
adversarial replay test (below) is only honest if it replays against a
world where `entity_matches` genuinely hasn't changed between the
original decision and the replay -- which is true for every scenario
this checkpoint can construct (nothing in this system ever re-runs Phase
2 mid-session), so the test's guarantee is stated precisely as "same
decision reproduced when entity resolution hasn't changed," not "same
decision reproduced no matter what."

## What this spec deliberately does not settle

Per the user's own instruction -- this is a specification and an
adversarial reasoning pass, not an implementation plan:

- Whether `Decision` becomes a new event type, a new store, or lives
  inside `Action.preconditions` expanded -- a storage-mechanism question,
  explicitly deferred.
- Whether the orchestrator/action-loop wiring gap (Controller/Risk never
  reaching an executor) gets fixed as part of this work or separately.
- Whether `logic_version`/`policy_version` are hand-maintained strings
  (cheapest, proposed above) or something more structured.
- Any actual code change to `verdict.py`, `policy/engine.py`,
  `action/models.py`, or anywhere else.

The next decision, per the user's stated sequencing, is whether any of
this becomes real -- and if so, how much of it (a minimal
`decision_id + world_as_of + logic_version` versus the full candidate
model above) -- not predetermined by writing this document.

## Implementation (this checkpoint)

Implemented, minimally, per the user's explicit go-ahead following the
`logic_version` resolution above: `financial_system/decisions/` (`models.py`'s
`DecisionRecord`, `store.py`'s insert-only `DecisionStore`), version
constants (`RECOVERY_LOGIC_VERSION`, `POLICY_RULES_VERSION`), and a purely
additive `decisions`/`world_as_of` parameter pair on
`action/loop.py::run_action_loop_v2` (both default `None`; every existing
caller's behavior is unchanged). A `DecisionRecord` is written exactly
when `policy_decision.outcome == "ALLOW"` -- question 1's definition of
consequential, applied literally, not approximated. Controller and Risk
were not touched, per the user's explicit instruction -- `agent` will
only ever read `"recovery"` in any `DecisionRecord` this code can
currently produce, honestly reflecting that only Recovery reaches an
executor today.

**A real bug the adversarial replay test caught, not a hypothetical
scenario:** the first implementation stamped `world_as_of` *after*
`execute_action_with_events()` returned. Since that call also appends the
attempt's own `ActionOutcomeObserved` event, replaying at that recorded
cutoff caused `project(events, as_of=world_as_of)` to already include the
very outcome the decision was supposedly made *before* -- the replay
returned `DO_NOT_RETRY` for a decision stored as `RETRY`. Fixed by
capturing `reasoning_time` immediately before `evaluate()`/
`execute_action_with_events()` run, not after. This is exactly the
failure mode `TEMPORAL_ADVERSARIAL_REVIEW.md`'s whole discipline exists
to catch, one layer up: a plausible-looking implementation that gets the
*direction* of a temporal boundary backwards, caught by actually trying
to replay against it rather than trusting the field was populated
correctly because it compiled.

`financial_system/decisions/adversarial_test.py`, all against the real
pipeline: a consequential (RETRY) decision is recorded with a real
`action_id` link (verified via a new `ActionStore.get_by_action_id()`,
added because none of the existing lookup paths could verify this
honestly); a non-consequential (REVIEW) decision produces zero
`DecisionRecord` rows; the Decision-Action link resolves to the same
`case_id`; and historical replay -- rebuilding state via `project(events,
as_of=world_as_of)`, reusing `entity_matches` as-is per this document's
own scoped claim -- reproduces the stored `decision`/`decision_score`/
`reason` exactly. All 4 gates PASS. Every prior checkpoint (Phase 10,
Stage 3, Stage 4, `attempt_runner.py`, `temporal_adversarial_runner.py`)
re-run unchanged after this change.
