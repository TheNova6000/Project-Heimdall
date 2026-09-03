# PRD — Financial Agentic Operating System

## What we're building

An agentic system that sits on top of a shared financial world model and answers
three questions about the same stream of payment events: *is this risky?*, *does
this reconcile?*, *can this failed payment be recovered?* — using one shared
investigation substrate (Discovery.AI) instead of three disconnected tools.
Built for the Razorpay AI Buildathon, targeting Track 2 (AI Risk Manager), Track 4
(AI Finance Controller), and Track 3 (AI Revenue Recovery) simultaneously through
one architecture (see `ARCHITECTURE.md`).

## Who this is for

The buildathon judges, evaluating: working code over slideware, measured
precision/recall/match-rate over cherry-picked demos, an audit trail over a black
box, and restraint (defense-only, bounded actions, honest exceptions) over
unconstrained autonomy. Secondarily: a merchant finance/risk team, as the
persona the demo narrates for.

## Problem

Payment platforms generate three separate, expensive problems out of the same
underlying event stream — fraud, unreconciled money, and lost revenue from failed
payments — and teams typically solve them with three unrelated tools that never
share context. A shared device flagged by risk tooling is invisible to the
reconciliation team; a payment failure pattern visible to recovery tooling never
informs risk scoring. Nothing explains *why* a number is what it is beyond a
dashboard metric.

## What "done" looks like for the buildathon submission

1. A synthetic financial universe (`financial_system/data/`, already generated —
   1000 payments, 610 settlements, 27 fraud-ring customers, 160 recovery cases)
   with a held-out ground-truth answer key.
2. Ingestion → Financial State → Entity Resolution → Financial Graph pipeline
   running against that data, producing a queryable Neo4j graph.
3. One working Controller investigation end-to-end: reconciliation exception →
   `open_investigation()` → Discovery.AI decomposition → explanation, backed by
   real evidence, scored against `reconciliation_labels.csv`.
4. Risk and Recovery agents built on the same `AgentVerdict` contract, each scored
   against their respective ground truth (precision/recall for Risk, recovery
   rate + false-retry rate for Recovery).
5. A Policy Engine gating every `proposed_action` (ALLOW/REVIEW/DENY), with actions
   simulated (logged), not executed against a real payment API.
6. A demo that narrates 3 payments through all three lenses (see `ARCHITECTURE.md`
   §Demo story) plus the measured metrics table.

## Explicit non-goals (buildathon scope)

- No real Razorpay API calls that move money — everything is simulated/logged.
- No rebuild of Discovery.AI's View/Projection layer — direct Cypher reads
  filtered by relation family instead (see `ARCHITECTURE.md` §3).
- No production auth/multi-tenant concerns — single demo session is enough.
- No mobile/responsive polish — a working demo UI, not a shipped product.

## Success metrics (what the demo actually reports)

- Risk: precision, recall, false-positive rate on `risk_labels.csv`, including
  performance on the benign-shared-device traps specifically.
- Controller: match rate, and of the unmatched, the honest-exception rate against
  `reconciliation_labels.csv.is_explainable`.
- Recovery: recovery rate and false-retry rate against
  `recovery_labels.csv.retry_would_succeed`.
- Every verdict traceable to evidence — audit-trail completeness isn't optional,
  it's graded as part of Track 1/2's stated bar.
