# Future Architecture: The Intelligence Engine

This document exists to separate **architectural vision** from
**deadline-critical implementation**. Everything cited elsewhere in this
repository — Controller's 555/610 match rate, Risk's 100%/96.3%/0%, Recovery's
100%/87/87/39.6%, the event-sourcing and decision-provenance machinery — is
built, verified, and frozen. Nothing below is implemented. Nothing below
should be inferred as implemented from the diagrams alone.

## Where the current system stops

Today, intelligence in this system looks like:

```
Domain rules (Risk / Controller / Recovery, each independent)
     +
Discovery.AI investigation, invoked narrowly, per-domain, when deterministic
evidence runs out
     +
Policy rules
```

This is real, bounded, and auditable — and it's enough to demonstrate the
full Observe → Understand → Investigate → Decide → Act → Verify loop, which
this repository does, with a live world-state change and a fresh, correct
re-evaluation as the proof.

What it is *not* yet: a shared reasoning substrate. Each domain agent
investigates in isolation. There is no mechanism for one domain's finding to
inform another's investigation, and no explicit representation of
uncertainty beyond a single confidence float carried for audit only.

## The next evolution

```
                    FINANCIAL WORLD
                          |
                    EVENT HISTORY
                          |
                          v
                    WORLD MODEL
                          |
            +-------------+-------------+
            |             |             |
          RISK        CONTROLLER     RECOVERY
            |             |             |
            +-------------+-------------+
                          |
                     OBSERVATION
                          |
                          v
                 INTELLIGENCE ENGINE
                          |
             +------------+------------+
             |            |            |
         QUESTION      EVIDENCE     CONTEXT
             |            |            |
             +------------+------------+
                          v
                     INVESTIGATION
                    (recursive reasoning,
                     shared across domains)
                          |
                          v
                       FINDINGS
                          |
                  FACT / INFERENCE /
                  HYPOTHESIS / UNKNOWN
                          |
                          v
                   COMPOUND FINANCIAL CASE
                  (Risk + Controller + Recovery
                   findings reasoned over together,
                   not merged into one score)
                          |
                          v
                       VERDICT
                          |
                       POLICY
                          |
                        ACTION
                          |
                       OUTCOME
                          |
                    VERIFICATION
                          |
                          +----------------> back into WORLD
```

Concretely, four upgrades, none implemented here:

**A — Investigation as a shared mechanism.** `InvestigationRequest ->
Investigation -> Evidence -> Findings -> InvestigationResult` becomes one
reusable pipeline Risk, Controller, and Recovery all call into, instead of
each domain wiring `investigate_evidence()` independently. The recursive
decompose-retrieve-evaluate loop Discovery.AI already has generalizes to
finance the same way `financial_state_retriever.py` already generalized
retrieval — this is the natural continuation of that work, not a new idea.

**B — Compound reasoning, not compound scoring.** Today's `CompoundCase`
(Phase 8) correctly keeps Risk/Controller/Recovery verdicts whole and
detects a small, explicit set of cross-domain conflicts. The next version
lets a compound case carry open questions across domains: "Risk says HIGH,
Recovery says RETRYABLE, Controller says UNEXPLAINED — what does the
combined state imply?" is a genuinely different, richer question than three
independent verdicts sitting side by side.

**C — Computational uncertainty.** Not a single `investigation_confidence`
float, but explicit `FACT / INFERENCE / HYPOTHESIS / UNKNOWN /
CONTRADICTION` states per claim, with evidence relationships (support/
contradict) that a downstream reader — human or Discovery.AI itself — can
traverse, not just read as a number.

**D — Outcome-driven re-evaluation as a first-class loop**, not a
side-effect of re-running a function. The system already proves the
mechanics of this today — `attempt_runner.py`'s scenario 1 is a real
payment whose retry succeeds, and a fresh, independent Recovery call
concludes `DO_NOT_RETRY` with no special-case code anywhere. What's missing
is generalizing that specific, proven loop into something Risk and
Controller share too, not just Recovery.

## Why this isn't being built for this submission

Two reasons, both concrete, not just "out of time":

1. **Every upgrade above touches Risk, Controller, and Recovery's actual
   decision logic simultaneously.** This repository's own discipline,
   applied consistently for the entire duration of this project, has been:
   verify a boundary, freeze it, move to the next one, never touch a
   working, measured result without a specific, deliberate reason. Building
   this now would mean three domains' verified numbers (555/610, 100%/96.3%/0%,
   87/87/39.6%) are simultaneously in motion two days before judging.
2. **It isn't what's being evaluated.** The buildathon's judging
   parameters — Problem Taste, Build Quality, AI Judgment, Failure
   Recovery — and the Revenue Recovery track's own bar (measured recovery,
   compliant escalation, stopping rules, an audit trail) are already met by
   what's built. A more ambitious intelligence architecture that isn't
   finished and provable by the deadline doesn't move any of those; a
   finished, verified system that also has a specific, well-reasoned next
   architectural step on record does.

## What this document is for

To show the vision was thought through deliberately, not omitted by
oversight — the same reason this repository already names, explicitly,
every other deliberately-deferred piece (the double-entry ledger,
settlement reversal, event-sourced reasoning history, full temporal pinning
of entity resolution). This is one more entry in that list, written before
being asked "what's next," not after.
