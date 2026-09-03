# AI Revenue Recovery — Submission Narrative

Primary track: **AI Revenue Recovery**. Secondary capability shown in the
same demo: **AI Finance Controller**. Supporting capability: **AI Risk
Manager**. One financial world, three domain agents, one investigation
layer, one policy/action boundary — the pitch zooms into Recovery, the
architecture visibly shows the rest is real, not implied.

Every claim in this script is tagged `[PROVEN: <where>]`. Nothing here
says anything `PRODUCT_DEMO_REVIEW.md`'s own PROVEN/GENERAL-CLAIM table
wouldn't already back. Written for a 5-minute pitch video plus the
architecture-documentation submission, mapped explicitly to the four
judging parameters: **Problem Taste, Build Quality, AI Judgment, Failure
Recovery**.

## The pitch script (5:00)

**0:00-0:25 — Problem Taste: the real problem, stated precisely**

> "Every payment platform loses revenue to failed payments that were
> actually recoverable. The naive fix — retry everything — creates a
> second problem: duplicate charges, wasted gateway calls, and retries on
> payments that were never going to succeed. The real problem isn't
> 'retry failed payments.' It's: **which failures are worth retrying,
> when do you stop, and can you prove afterward exactly why the system
> did what it did.**"

Not "an AI that retries failed payments" — that's commodity, and
Razorpay's own product direction already has retry/routing intelligence
for recurring payments. The differentiated claim is the *reasoning and
provenance* around the retry decision, not the retry itself.

**0:25-1:10 — Architecture, zoomed to Recovery, showing the shared world**

Show the diagram:

```
                 FINANCIAL WORLD (event-sourced, temporally honest)
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       RISK       CONTROLLER     RECOVERY   <- this pitch
          │            │            │
          └────────────┼────────────┘
                       ▼
                  DISCOVERY.AI (investigation, never decides)
                       │
                       ▼
                    POLICY  ->  DECISION RECORD  ->  ACTION  ->  OUTCOME  ->  back to WORLD
```

> "Recovery isn't a standalone bot. It reasons over the same graph Risk
> and Controller do, and a real cross-domain conflict check catches cases
> a retry-only system would miss entirely."

`[PROVEN: 139 real compound cases across all 1000 payments, 113 with
both Risk and Controller verdicts, 25 real detected conflicts — Phase
8]`.

**1:10-2:40 — The live demonstration: a world that changes, and a system
that notices**

Run it live, not scripted output — this is the single most important
5-minute investment: it's the concrete proof of "agentic," not a claim
about it.

```
Payment fails (technical_failure)
      |
Recovery: RETRY  -- decision_score = 0.85, the CATEGORY's own historical
                     base rate, never a per-instance guess
      |
Policy: ALLOW (R3_RECOVERY_RETRY_ALLOW)
      |
Action executes -- a DecisionRecord is written: world_as_of, logic_version,
                    policy_version, linked to the real Action it authorized
      |
Gateway responds: SUCCESS
      |
ActionOutcomeObserved -- a new, durable, timestamped world fact
      |
Payment.status flips to "success" -- via projection, not a hand-written patch
      |
Fresh Recovery call, same payment, brand-new graph built from the changed state
      |
Recovery: DO_NOT_RETRY -- "payment is not currently failed -- nothing to recover"
```

> "No code anywhere special-cases 'this was a successful retry.' The
> agent simply receives a world in which the payment already resolved,
> and answers honestly. That's the difference between a retry loop and a
> system with temporal memory."

`[PROVEN: ATTEMPT_MODEL_SPEC.md's acceptance test, attempt_runner.py
scenario 1, DECISION_PROVENANCE_SPEC.md's historical-replay gate — all
against a real, repeatable class of payment, not a cherry-picked one]`.

**2:40-3:25 — AI Judgment: the honest number, framed as a strength**

This is the paragraph that must not overclaim, and turns out to be the
strongest AI-Judgment story available:

> "We do not claim the system predicts which individual retry will
> succeed. It can't, and pretending otherwise would be dishonest. What it
> does: classify a failure's *category* as recoverable (100% accuracy
> against ground truth), retry every recoverable case (100% recovery
> rate — which is a mathematical consequence of that classification
> rule, not a prediction claim), and accept that **39.6% of those
> retries genuinely fail** — a number that matches the categories' own
> weighted historical base rates (39.3% expected) almost exactly. Zero
> percent would require an oracle. We built the honest number instead."

`[PROVEN: Phase 7 done-check — 100% category-recoverability accuracy,
100% recovery rate (87/87), 39.6% false-retry rate vs. 39.3% expected]`.
This is also, directly, the **AI Judgment** criterion answered on the
spot: `decision_score` is always the deterministic category base rate;
Policy structurally has no field for `investigation_confidence`
(`policy/engine.py`'s own docstring) — an LLM's confidence cannot
authorize a financial action, checked by a real adversarial test
(`policy/runner.py` case 5: 0.99 confidence does not authorize a 0.20
decision_score action).

**3:25-4:05 — Discovery.AI: the actual differentiator**

> "Razorpay already has recovery intelligence in its own product
> direction. What's different here is what happens when a failure
> doesn't fit the known taxonomy: instead of guessing, the system opens a
> bounded, graph-grounded investigation — Discovery.AI reads only the
> evidence structurally connected to this payment, separates FACT from
> INFERENCE from HYPOTHESIS, and hands back a narrative. That narrative
> is *never* allowed to decide anything. `decision`, `decision_score`,
   and `proposed_action` are always the deterministic agent's own."

`[PROVEN: 4A 555/610 zero-LLM match rate against ground truth (91.0%),
re-verified fresh this session and confirmed unchanged whether
Discovery.AI is enabled or not -- Controller's decision structurally
never changes based on investigation output. The original Phase 5
done-check's "607/610" figure predates this boundary being tightened
and does not reproduce against the current code; corrected here rather
than carried forward. 4B's separately-scored 40/40 stratified-sample and
232/610-at-99.1% figures (a different metric -- InvestigationResult.status
vs. ground truth, not AgentVerdict.decision) were not re-verified this
session and are cited as documented, not re-confirmed]`. Show the boundary explicitly:
`investigation_confidence` lives on the verdict for audit only, never
read by Policy.

**4:05-4:35 — Secondary capability, in one breath: Controller and Risk
are real, not implied**

> "The same substrate runs Controller — 555 of 610 real settlements
> reconciled automatically, zero LLM calls, with a genuine accounting
> finding this week: 77 of those settlements have an internal
> gross-minus-fee-minus-tax arithmetic inconsistency that operational
   reconciliation alone would never catch. And Risk — 100% precision,
   96.3% recall, zero false positives on 16 deliberately-planted benign
   traps."

`[PROVEN: Phase 5, Phase 6, FINANCIAL_ACCOUNTING_BOUNDARY_REVIEW.md]`.

**4:35-5:00 — Close: provenance and honest limits**

> "Every consequential decision this system makes is durably recorded —
> what was decided, against what world snapshot, under which policy
   version, linked to the action it authorized. We tested that with a
   replay: rebuild the world from the event log, re-run the exact
   reasoning, and it reproduces the stored decision exactly. We're not
   claiming this generalizes to every payment system on day one — we're
   claiming we proved it on this one, and we know precisely where the
   proof currently ends."

## Failure Recovery: what actually broke, and how it was found

Judged explicitly on this criterion — real incidents, not manufactured
ones, each caught by a test built specifically to attack the claim, not
discovered by accident:

1. **A replay test caught a real, direction-reversed bug in Decision
   Provenance.** The first implementation stamped a decision's
   `world_as_of` *after* the authorized action executed. Since the
   action's own outcome event landed before that timestamp, replaying at
   the recorded cutoff caused the world snapshot to already include the
   retry's own result — a stored `RETRY` decision replayed back as
   `DO_NOT_RETRY`. Fixed by capturing the timestamp before reasoning
   runs, not after. `[DECISION_PROVENANCE_SPEC.md]`.
2. **Stage 4's re-entry gate exposed a real ontology gap, not just a
   bug.** After a successful retry, asking Recovery again produced
   `"INVESTIGATE / unrecognized failure_reason=None"` — an honest
   answer, but a confusing one. Root cause, found by tracing the actual
   code: Recovery checked `failure_reason` but never checked whether the
   payment was still failed at all. Fixed with a general status check,
   deliberately *not* a "successful retry" special case — verified to
   produce the identical answer whether resolved on attempt 1, 2, or 5.
   `[ATTEMPT_MODEL_SPEC.md, Stage 4 Gate 3]`.
3. **A boundary review corrected its own earlier finding.** An initial
   pass claimed 19 of 610 settlements had a payment-sum inconsistency.
   Building the real check (not just eyeballing a script) revealed the
   naive sum wasn't deduplicating repeated settlement-payment links —
   those 19 were entirely the already-known `duplicate_record` anomaly,
   not a second, independent gap. Corrected in the same document, not
   quietly dropped. `[FINANCIAL_ACCOUNTING_BOUNDARY_REVIEW.md]`.

The pattern across all three, worth saying to the panel directly: every
one was found by a test built to attack a specific claim, not by manual
inspection — and every one was corrected in the same document that made
the original claim, not patched over silently.

## Explicitly defensible limitations (have these ready, don't wait to be asked)

- **Simulated execution, not a live gateway.** `action/simulator.py`'s
  own documented boundary — no real payment API is ever called. Framed
  honestly as the harness this architecture is built to plug a real
  gateway into, not a claim of production readiness.
- **`decision_score` is a category base rate, never a per-instance
  prediction.** Stated as a design decision, not hidden as a limitation
  — 0% false-retry rate would require an oracle.
- **Reasoning/Verdicts are not event-sourced.** Only Observational and
  Action facts are `as_of`-reconstructable; "what did the system decide
  last Tuesday" is not answerable today, and `REASONING_TEMPORAL_REVIEW.md`
  explains precisely why that's a deliberate boundary, not an oversight.
- **`entity_matches` is not pinned by `world_as_of`.** Historical replay
  is proven correct conditional on entity resolution being unchanged
  since — named explicitly in `DECISION_PROVENANCE_SPEC.md` before
  implementation started, not discovered after.
- **No ledger.** A deliberate, researched decision
  (`FINANCIAL_ACCOUNTING_BOUNDARY_REVIEW.md`), not a missing feature —
  building one would have been a second, unproven subsystem competing
  with this session's actual, proven architecture for the remaining
  time.

## Build Quality, in one line for the README

Insert-only event/action/decision stores throughout (no financial fact
is ever edited, only superseded); a closed event taxonomy enforced at
the write boundary; 30+ real adversarial gates across ten dedicated test
files, all passing, all re-run after every change this session touched;
zero mocked financial logic anywhere in the decision path.
