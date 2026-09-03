# Architecture Review — Phases 0–10

Written after Phase 10, before Phase 11, at the user's explicit request to
stop and interrogate whether the implemented system is actually the system
`ARCHITECTURE.md` describes — not to redesign, and not another pass/fail
report. Every claim below is grounded in the actual code (file:line), not
the design docs, verified in this session before writing.

## What actually held (brief, since this has been proven repeatedly)

The one boundary this whole build was organized around — deterministic
intelligence decides, investigative intelligence only explains — held
structurally at every phase, not just by convention:

- `decision_score` is always agent-computed; `investigation_confidence` is
  carried on `AgentVerdict` for audit only, and `PolicyDecision` doesn't
  even have a field for it (`policy/engine.py`) — structurally impossible to
  read, not just unread by convention.
- Phase 9's boundary test proved this experimentally: `investigation_confidence=0.99`
  with `decision_score=0.20` still resolves to `REVIEW`, not `ALLOW`.
- Provenance holds end to end for the *deterministic* path: every
  `financial_state` row traces to a raw CSV row (Phase 1), every graph edge
  traces to a `financial_state` row or an `entity_matches` record (Phase 3),
  every `AgentVerdict.evidence` traces to graph node ids (Phases 5–7).
- Honest uncertainty is real, not decorative: `PARTIALLY_EXPLAINED` never
  fires, `R8`/`R10` policy rules never fire, the benign-shared-device trap
  produces 0% false positives, and every one of these gets reported as a
  finding rather than hidden.

This part of the system is solid. The review below is about what's *not*
yet built, which is a different and more important question at this point.

## The central finding

**The system is a stateless, read-only reasoning function over a frozen
snapshot. It is not yet a system that closes on the real world.**

This is the honest answer to the user's question 7 ("what is verification")
and question 8 ("what happens when reality contradicts expectation"), and it
changes how the Observe→...→Verify diagram should be read.

Concretely, verified in code:

- `financial_state.db` and `financial_graph.db` are built once from the
  static Phase 0 CSVs and never written back to. No action taken anywhere
  in Phases 5–10 ever updates a payment's status, a settlement's net
  amount, or any other fact in `financial_state`.
- Phase 10's `verify_retry()` (`action/simulator.py`) checks a **held-out
  ground-truth oracle** standing in for a gateway response — by necessity,
  since there is no live gateway to mutate. That's an honest simulation
  boundary, already documented. The deeper gap is what's *missing*, not
  what's simulated: even in principle, there is no code path where a
  verified outcome gets written back into `financial_state`/the graph, so
  Controller could re-evaluate a settlement in light of a payment that just
  recovered. The loop closes *within one process's memory*, once, and then
  the fact is gone.
- Neither `CompoundCase` (Phase 8) nor `ActionCase` (Phase 10) is persisted
  anywhere — confirmed by grep, zero hits for persistence code in
  `orchestrator/` or `action/`. Compare this to Phase 4's `batch_4b.py`,
  which does persist every case to JSONL specifically so a run survives an
  interruption. Phases 8 and 10 don't have that: run the orchestrator twice,
  get two independent in-memory results with no record either happened.

So "Verify" in the diagram is real and proven at the *decision* layer
(Phase 9's policy gate, Phase 10's retry-or-escalate loop) but not yet real
at the *world* layer (nothing observes a changed world, because nothing can
change it yet). For the buildathon pitch, this is an important, precise
thing to be able to say out loud rather than let the diagram imply more than
the code does.

## Three secondary findings, each verified in code this session

**1. `AgentVerdict.reason` flattens the FACT/INFERENCE/HYPOTHESIS distinction
Phase 4 built.** `InvestigationResult` carefully separates `facts`,
`inferences`, and `hypotheses` (`discovery_adapter/models.py`) — but every
one of `controller.py:56`, `risk_agent.py:61`, and `recovery_agent.py:55`
does `reason = investigation.narrative` when an investigation ran,
discarding the deterministic reason and collapsing the three tiers into one
string. Not a bug — `reason` was always meant as a human-readable summary —
but it means a downstream consumer of `AgentVerdict` (Policy, the
orchestrator, a future UI) has no way to tell "this is a deterministic
fact" from "this is Discovery.AI's synthesized read" once an investigation
has run. Worth a `reason_tier` field if this becomes demo-facing.

**2. Phase 8 and Phase 10 don't share verdicts, and would double-invoke
Discovery.AI if both had `investigate=True` on.** `orchestrator.py` calls
`run_recovery_for_payment()` for its Recovery verdict; `action/loop.py`
independently calls `run_recovery_for_payment()` again for the same
payment (`loop.py:63`). Both currently run with `investigate=False`, so
today this is just redundant computation, not a real cost. But it's a
genuine integration gap: there's no single place that computes a verdict
once and hands it to both the compound-case merge and the action loop, so
turning on `investigate=True` in both paths would fire two separate
investigations for the same payment.

**3. `Action` has no independent identity.** It's a string
(`proposed_action`/`action_taken`, e.g. `"RETRY_PAYMENT"`) with no
`action_id`, no timestamp, no recorded precondition, living only inside
`ActionAttempt`. The user's proposed structured shape (`action_id, case_id,
actor, authorization, preconditions, intended_mutation, timestamp`) is the
right one for a system that will eventually call a real API — idempotency
(don't double-execute if the loop runs twice), a genuine timestamped audit
trail, and a place to record what precondition was checked all need it.
Today's string is sufficient for a simulated, single-process demo and
insufficient for anything beyond that.

## Scope-boundary findings (real, not flaws — worth stating precisely)

- **Risk is a single-signal detector.** It answers "is there a suspicious
  device-sharing network," full stop. A fraud ring that doesn't share a
  device (distinct devices, same operator) is structurally invisible to
  it — there's no velocity-without-device-sharing or
  amount-anomaly-without-network signal anywhere in `risk/signals.py`. This
  is honest scope, not an oversight, but the buildathon pitch should name it
  as "detects one real, common fraud pattern" rather than "detects fraud."
- **Reconciliation finds one cause per settlement, never a combination.**
  `reconcile_settlement()` computes a single `duplicate_adjustment` number;
  a settlement with *two* overlapping anomalies (say, a duplicate line item
  *and* an unrelated fee discrepancy) would only get the first explained,
  the rest folded into `unexplained_amount` — untested, since the corpus
  never generates two anomalies on one settlement.
- **Entity Resolution's probabilistic/disambiguation tiers remain
  unexercised** (documented back in Phase 2, still true) — still real code,
  still never actually run against an ambiguous case.
- **No concurrency or temporal skew exists to test against**, because the
  whole system runs single-threaded and synchronously against one static
  snapshot per process. The user's "what if two agents disagree because
  they're looking at different temporal snapshots" question doesn't have a
  wrong answer yet — the current architecture hasn't reached the point
  where that question is even askable. Worth being precise about the
  difference between "solved" and "not yet reachable."

## What this means for Phase 11

Nothing above invalidates Phases 0–10's actual results — the metrics are
real, the boundary held, the findings pattern (build, verify, report
honestly, don't manufacture passing numbers) is consistent throughout. The
review's value is naming precisely what layer of the "operating system"
diagram is proven versus illustrative, so Phase 11's demo and any buildathon
write-up can say exactly that: the **decision loop** (Observe → Understand →
Investigate → Decide → Policy) is real, tested at scale, and experimentally
proven to keep Discovery.AI in its lane. The **world-mutation loop** (Act →
changed world → re-Observe) is currently simulated at the boundary where a
real system would need a live gateway and a write-back path — a clearly
scoped, honestly named next increment, not a gap in what's already built.
