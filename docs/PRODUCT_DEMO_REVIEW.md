# Product / Demo Review

Written per the user's explicit direction: architecture is frozen, the
accounting boundary is closed, and the question moves from "can this
system support the intelligence loop" (yes -- ten phases plus five
temporal/provenance/accounting checkpoints all proven this session) to
"what is the smallest product experience that makes that architecture
undeniable to a judge." No UI code, no implementation -- this is the
artifact the user asked for before either begins. Every number below is
either re-verified this session or read directly from `Phases.md`'s own
done-check results (Phase 4-10), never invented for this document.

## 1. What is the product?

Not "an event-sourced financial agent." Precisely, grounded in what
actually runs today:

> **A financial intelligence system that detects financial anomalies
> across reconciliation, fraud, and recovery domains; investigates why
> they happened using a graph-grounded LLM investigator when
> deterministic evidence runs out; makes domain-specific, auditable
> decisions; enforces policy before any consequential action executes;
> executes and verifies the action; and re-evaluates the world once the
> outcome is known -- with every step traceable back to the exact
> evidence, decision version, and world state it was made against.**

The one-sentence version, for a judge who has thirty seconds: **it
doesn't just flag that money looks wrong -- it explains why, decides
what to do, does it, and proves it was right to.**

## 2. What should the judge see -- one causal story, corrected

The user's proposed arc was almost exactly right, and the correction is
itself worth showing, not hiding, because it's more honest than the
original pitch:

```
PAYMENT fails (technical_failure)
       |
Recovery: RETRY (category base rate 0.85, not a per-instance guess)
       |
Policy: ALLOW (R3_RECOVERY_RETRY_ALLOW)
       |
Action executes -- DecisionRecord written (world_as_of, logic_version, policy_version)
       |
Gateway responds: SUCCESS
       |
ActionOutcomeObserved -- a new, durable world fact
       |
State changes: Payment.status flips to "success"
       |
Fresh observation: SAME payment, asked again, from a NEW graph built from the changed state
       |
Recovery: DO_NOT_RETRY -- "not currently failed -- nothing to recover"
       |
(no special-case code for "this was a successful retry" anywhere -- the
 agent simply received a world in which the payment had already resolved)
```

Every step in this chain is real, proven this session, on real payment
`pay_3a5beb26ef` (or any technical_failure/retry-succeeds payment --
this is a repeatable class of case, not a cherry-picked one):
`ATTEMPT_MODEL_SPEC.md`'s acceptance test, `attempt_runner.py` scenario
1, and `DECISION_PROVENANCE_SPEC.md`'s own historical-replay gate all
exercise exactly this sequence.

**The correction, worth making explicitly rather than silently fixing in
the demo script**: the user's original arc continued past a *second*
gateway failure into "Recovery no longer recommends retry." That
specific continuation is not true of the system as built. Checked
directly: `recovery/signals.py::compute_recovery_signals()` never reads
`attempt_number` or any prior-attempt history for the *same* payment --
only `failure_reason` and whether a *sibling* payment on the same order
already succeeded. If Recovery were asked a third time about a payment
that failed twice, it would give the **identical** `RETRY` recommendation
it gave the first time, because nothing currently feeds "we already tried
and it didn't work" back into Recovery's own signals -- `MAX_ATTEMPTS=2`
in `action/loop.py` is what actually stops the loop (an operational cap,
not a learned judgment), and the loop escalates to a human rather than
asking Recovery again. This is a real, precise limitation worth having an
honest answer ready for, not a demo-breaking gap -- but the compelling
arc to actually show a judge is the **success** path above, not a repeat-
failure path, because the success path is where the system's behavior
genuinely changes for a reason a judge can see (the world changed), while
the repeat-failure path would show the system giving the same answer
twice for a reason a sharp judge could reasonably ask about.

## 3. What should NOT be shown

Exactly the user's list, confirmed against what this session actually
built: `EventStore` internals, `project()`'s implementation, idempotency
key formatting, SQLite repository details, the temporal ontology
documents, the migration stage numbering. All of that is **proof
underneath the product** -- six architecture-review documents and eleven
adversarial-test files exist specifically so a judge doesn't have to
trust a claim on faith, but the documents themselves are the trust
mechanism, not demo content. A judge should see the *outcome* of that
rigor (a system that can prove its own history is self-consistent) without
sitting through the derivation.

## 4. What claims can we legitimately make -- PROVEN ON DATASET vs. GENERAL CAPABILITY

| Capability | PROVEN ON DATASET (cite the number) | GENERAL CLAIM (do not make this) |
|---|---|---|
| Reconciliation | 555/610 match rate (91.0%), 47/50 honest-exception rate (94.0%), **0 LLM calls**, confirmed unchanged with Discovery.AI enabled (`decision` never changes based on investigation output, by design) -- corrected from Phase 5's original documented figure, which does not reproduce against the current code | "the system reconciles any settlement" -- untested outside this dataset's anomaly taxonomy |
| Fraud/risk detection | 100% precision, 96.3% recall (26/27 -- the one miss has zero payment records, no signal could catch it), 0% FPR on 16 benign-shared-device traps (Phase 6) | "detects fraud rings" without qualifying "device-sharing-burst pattern, this dataset's specific construction" |
| Recovery classification | 100% category-recoverability accuracy, 100% recovery rate (87/87 -- a mathematical consequence of retrying every recoverable category, stated as such in Phase 7's own done-check, not evidence of prediction), 39.6% false-retry rate matching the categories' own 39.3% expected base rate | "predicts which retries will succeed" -- explicitly false; `decision_score` is a category base rate, never a per-instance guess, by design |
| Cross-domain reasoning | 139 real compound cases, 113 with both Risk and Controller verdicts, 25 real detected conflicts, one concrete example (`pay_07d6aac5f3`: Controller PASS + Risk HOLD, a reconciliation-only view would have missed it) (Phase 8) | -- |
| Policy enforcement | 5/5 required cases including the two that matter most (0.99 investigation_confidence cannot authorize a 0.20 decision_score action), applied to all 1000 payments' real compound cases (Phase 9) | -- |
| Durable action + verification | 5/5 required cases on real payments, full 160-payment batch, every number cross-validated against Phase 7's independently-computed report (Phase 10) | "executes real payment retries" -- simulated throughout, `action/simulator.py`'s own explicit, documented boundary; never a live gateway call |
| Investigation (Discovery.AI) | 4A: 555/610 zero-LLM (`_deterministic_pass()` calls the same `reconcile_settlement()` Controller uses, confirmed to carry the identical correction -- see Reconciliation row above); 4B: 40/40 stratified sample correct, 232/610 of the full corpus at 99.1% before a quota/process interruption -- this figure uses a separate code path (LLM-updated `InvestigationResult.status`, not `reconcile_settlement()` alone) and was not re-verified this session | "investigates any financial anomaly" -- validated on this dataset's specific `reconciliation_labels.csv` taxonomy, at partial full-corpus scale for 4B |
| Temporal reconstruction (`as_of`) | 4/4 gates: correct state before/at/after a retry outcome, cross-connection determinism proven on 1000 real payment rows | "full audit history" -- Reasoning/Verdicts are NOT event-sourced (`REASONING_TEMPORAL_REVIEW.md`'s own finding); only Observational + Action facts are `as_of`-able |
| Decision provenance | Historical replay reproduces a stored decision's `decision`/`decision_score`/`reason` exactly, on a real recorded consequential decision; 7/7 adversarial gates including a real timing bug the replay test itself caught and fixed | "full historical reproducibility" -- explicitly scoped: `entity_matches`/reference tables are NOT pinned by `world_as_of` (documented, not silently assumed away) |
| Accounting consistency | 77/610 real settlements (12.6%) fail `net = gross - fee - tax`, 62 of those inside the operationally-"clean" category -- a genuinely different class of finding than reconciliation alone produces | "a ledger" or "double-entry accounting" -- explicitly, deliberately not built; this is two invariant checks, not a value-conservation system |

The pattern worth stating once, plainly, because it's the strongest
single credibility signal available: **every "built but unexercised"
case in this project has been named as such at the moment it was found**
(Phase 2's probabilistic matching, Phase 4's `PARTIALLY_EXPLAINED`, Phase
7's alternate-success override, Phase 9's `R8`/`R10`, this session's
`entity_matches` temporal gap, the Reasoning-layer event-sourcing gap,
the settlement-reversal boundary) -- never hidden, never quietly dropped
from a report because it would have looked better unmentioned. A judge
who asks "what doesn't work" gets a real, specific answer instead of a
generic disclaimer, for every single capability in this system.

## What this review does not do

No UI is designed here. No script is written. No decision is made about
which of the true, provable stories above becomes the actual live demo
sequence versus a slide -- that's the next, separate step, and per the
user's own framing, it should follow this document rather than precede
it. This document's job was narrower: establish what's true, what's
provable, what's explicitly out of scope to claim, and which single
causal chain -- the retry-succeeds, world-changes, system-re-evaluates
sequence -- is the one worth building the demo around, corrected once
against what the architecture actually does rather than what would have
made the best story.
