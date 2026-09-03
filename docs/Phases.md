# Phases

Bottom-up, per the build order locked in with `ARCHITECTURE.md`. Each phase has
a concrete "done" check — don't start the next phase until the current one's
check passes for real, against `data/ground_truth/`, not by eyeballing output.

## Phase 0 — Synthetic financial universe ✅ DONE

`financial_system/data_generator/generate_dataset.py` → `financial_system/data/raw/`
(11 CSVs) + `financial_system/data/ground_truth/` (5 label files + case manifest).

**Done check:** script runs with a fixed seed, prints entity/case counts,
`entity_resolution_labels.csv` row count matches `bank_transactions.csv` row count.

## Phase 1 — Financial State

`financial_system/ingestion/` + `financial_system/financial_state/`. Ingestion
agents (Payment/Settlement/Bank/Refund/Fee/Order) parse `data/raw/*.csv` into
normalized records in a queryable store (SQLite is enough). Malformed rows go to
an explicit rejects log (`Rules.md`), never silently dropped.

**Done check:** every row in every raw CSV is either normalized or rejected-with-reason;
counts reconcile (e.g. `len(payments table) == len(payments.csv) - len(rejects)`).

## Phase 2 — Entity Resolution

`financial_system/entity_resolution/`. Solves the one genuinely hard linkage:
Settlement → BankTransaction (see `data/DATASET_DESIGN.md`). Deterministic pass
(exact UTR/amount+date) first, probabilistic pass (amount proximity + date
proximity + partial string match on `description`) for the rest, each producing a
`matches` edge with `confidence` + `evidence[]`. No LLM here — this is graph/
deterministic intelligence (`ARCHITECTURE.md` §0, kind 1–2).

**Done check:** precision/recall of produced `matches` edges against
`ground_truth/entity_resolution_labels.csv`, printed as numbers.

## Phase 3 — Financial Graph

`financial_system/financial_graph/`. Writes resolved entities/relations into
Discovery.AI's Neo4j using the relation types from `ARCHITECTURE.md` §1 (extend
`relation_types.py` with the `FINANCIAL` family here, additive only per `Rules.md`).

**Done check:** a manual Cypher query for one known payment returns its full
chain (Customer → Payment → Settlement → BankTransaction) correctly.

## Phase 4 — One investigation, end to end ✅ DONE

`financial_system/discovery_adapter/`: `FinancialStateRetriever` +
`open_investigation()`. Built as two passes, not one — 4A (deterministic,
zero LLM, always runs) and 4B (real Discovery.AI investigation, gated on a
configured LLM key). `GroundAgent` itself is never instantiated: its own
evidence-gathering call hardcodes Discovery.AI's `DEFAULT_RETRIEVERS` with no
override, so `open_investigation()` composes Discovery.AI's real unmodified
building blocks directly (`decide_next_step`, `gather_evidence(retrievers=
[FinancialStateRetriever])`, `synthesize_answer`) instead of patching
Discovery.AI's source. Zero changes to `vendor/discovery-ai`.

**Done check result:**
- 4A alone: 99.5% (607/610) on the full corpus, zero LLM calls. The 3 misses
  are all sub-₹1 `currency_conversion` gaps correctly auto-resolved as
  immaterial, not classification errors.
- 4B (real LLM, both Groq/Gemini/Cerebras key pools live): validated at three
  scales — 4 hand-picked cases, a 40-case stratified sample (100% correct,
  every case actually executed 4B), and 232/610 of the full corpus (99.1%
  correct) before a Groq daily-quota exhaustion + an unexplained external
  process kill stopped the run. All misses at every scale were the same two
  already-understood sub-₹1 `currency_conversion` settlements — full
  consistency across 4A-only and 4A+4B, and across every sample size tested.
- The anchoring fix (`investigate.py`'s `_run_4b` states 4A's exact computed
  gap in the question text) was necessary and load-bearing: unanchored, the
  LLM pattern-matched a plausible-looking fee onto an unrelated gap at 0.75
  confidence (29x off). Anchored, confidence genuinely tracks correctness
  (0.94 avg when EXPLAINED, 0.62 avg when UNEXPLAINED across the 40-case run).
- `FinancialStateRetriever` ranks by relevance and now actually respects
  `max_results` (previously ignored it, sending up to 18 facts per
  investigation regardless of Discovery.AI's `max_results_per_retriever=2`
  default) — verified: avg 4.8 offered vs. 2.0 used post-fix.
- `PARTIALLY_EXPLAINED` has never actually triggered at any sample size —
  same "built but unexercised" pattern as Phase 2's probabilistic-match path.
- A generalization of Discovery.AI's retriever contract (structured/bounded
  evidence as a first-class concept, not just ranked web search) is real and
  worth doing, but deliberately deferred — documented at
  `financial_system/discovery_adapter/RETRIEVER_CONTRACT_ISSUE.md`, not filed
  publicly, not implemented. The adapter-side fix already fully solves the
  problem for this system.
- `batch_4b.py` persists every case to JSONL as it completes (survived the
  external kill with zero data loss) but has no resume capability yet — a
  restart re-runs from case 1. Worth adding before any future full-corpus run.

## Phase 5 — Controller, complete ✅ DONE

`financial_system/reconciliation/`: `deterministic.py` (moved out of
`discovery_adapter` — Controller, not the investigation boundary, owns "what
actually happened") + `controller.py`. Every settlement gets an `AgentVerdict`;
Discovery.AI is called only when `status == UNEXPLAINED`, via the new
`discovery_adapter.investigate_evidence()` entry point (facts pre-computed,
no wasted re-run). `decision`/`proposed_action` come entirely from
`reconcile_settlement()`; `investigation_confidence` is carried for audit only.

**Done check result (original):** 607/610 match rate (99.5%), 99/102
honest-exception rate (97.1%), **0 LLM calls**. All 3 mismatches were the
same known sub-₹1 `currency_conversion` cases from Phase 4A.

**Correction (re-verified during buildathon-submission prep):** this
figure does not reproduce against the current code. `run_controller_for_settlement()`'s
`decision` field structurally never changes based on Discovery.AI's
investigation output (`controller.py`'s own boundary: "Discovery.AI's own
read of the same case never changes Controller's decision"), and several
reconciliation categories (`fee_discrepancy`, `partial_refund`, most of
`currency_conversion`) are `UNEXPLAINED` under 4A's arithmetic alone —
confirmed directly, `decision` stays `INVESTIGATE` for these even with
`investigate=True` and real LLM calls. The true, currently-reproducible
number is **555/610 match rate (91.0%), 47/50 honest-exception rate
(94.0%), 0 LLM calls** — verified fresh, unchanged with or without
Discovery.AI enabled. The original 607/610 figure most likely predates
this boundary being tightened to its current, correctly-audit-only form;
left here struck through in effect rather than silently edited, per this
project's own standing discipline.

## Phase 6 — Risk ✅ DONE

`financial_system/risk/`: `signals.py` (deterministic graph features) +
`scoring.py` (interpretable weighted formula) + `risk_agent.py`. Computed per
device with ≥2 sharing customers via **windowed burst detection** (most
payments in any 60-minute window), not naive whole-history averaging — a real
fraud-ring burst gets diluted to near-zero signal if a member's ordinary,
unrelated purchases on the same device are averaged in. `FinancialStateRetriever`
generalized to accept any `neighborhood_fn` (`risk_neighborhood()` alongside
Phase 4's `reconciliation_neighborhood()`) — a second real caller, not a
speculative abstraction.

**Done check result:** 100% precision, 96.3% recall (26/27 — the one miss has
*zero payment records at all*, no transaction-based signal could have caught
it), **0% false-positive rate on the 16 benign-shared-device traps**. Also
found and corrected: `DATASET_DESIGN.md`'s documented "new account" ring
signal is disconnected from ring membership in the actual generator code —
verified, not assumed, and reweighted down rather than pretended to work.

## Phase 7 — Recovery ✅ DONE

`financial_system/recovery/`: `signals.py` (a real decline-code taxonomy —
`is_recoverable` is category-level domain knowledge, a lookup, not inference)
+ `recovery_agent.py`. Preserves "recoverable ≠ should retry" explicitly:
`decision_score` for a RETRY is the category's own historical base success
rate, never a per-instance prediction of `retry_would_succeed` (which isn't
knowable in advance from anything in this system). An alternate-success check
(don't retry if another payment on the same order already succeeded) is built
and real, though unexercised — this corpus gives every order exactly one
payment attempt.

**Done check result:** 100% category-recoverability accuracy, 100% recovery
rate (87/87 — a mathematical consequence of retrying every recoverable
category, not evidence of prediction), **39.6% false-retry rate — verified to
match the categories' own weighted base rates (39.3% expected) almost
exactly**. This is the intended, honest behavior: 0% would require an oracle.

## Phase 8 — Financial Orchestrator + compound cases ✅ DONE

`financial_system/orchestrator/`: `events.py` (deterministic event
reconstruction from graph state, since no live event bus exists) +
`compound_case.py` (`CompoundCase` — Controller/Risk/Recovery verdicts kept
whole and labeled, never flattened into one score) + `orchestrator.py`.
Anchored on **Payment** as the connecting entity, since it's the one thing
linking to a settlement, a device, and a failure reason at once.

**Done check result:** run across all 1000 payments (zero LLM cost):
- 807 got a Controller verdict, 143 a Risk verdict, 160 a Recovery verdict
- **139 compound cases (≥2 verdicts), 113 with both Risk and Controller, 25 with a detected conflict**
- A real example the merge surfaced: `pay_07d6aac5f3` — Controller says PASS
  (settlement reconciles exactly), Risk says HOLD (device shared by 4
  customers, 9-payment burst in 60 minutes). A reconciliation-only view would
  never have flagged this payment at all.
- A real conflict the rules caught: Risk HOLD + Recovery RETRY on the same
  customer — "recommend REVIEW before executing the retry," never silently
  averaged into one score.

## Phase 9 — Policy Engine ✅ DONE

`financial_system/policy/`: `rules.py` (11 rules, first-match-wins, ordered
so a cross-domain conflict always overrides an individually-approving rule)
+ `engine.py`. `PolicyDecision` deliberately has no `investigation_confidence`
field at all — not filtered out, structurally absent, so no future caller can
read it as if it mattered to authorization.

**Done check result:** all 5 required cases pass, including the two that
matter most — case 4 proves `investigation_confidence` never changes the
outcome (0.1 vs. `None` both land on `ESCALATE`), and case 5's boundary test
proves a **0.99 confidence cannot authorize a 0.20 decision_score action**
(lands on `REVIEW` via `R4`, not `ALLOW`). Applied across all 1000 payments'
real compound cases (zero LLM cost): `{ALLOW: 784, ESCALATE: 189, BLOCK: 89,
REVIEW: 48}`, every single one traceable to one of 8 rules that actually
fired (`R8_RISK_REVIEW` and `R10_RECOVERY_DO_NOT_RETRY_ALLOW` built but
unexercised in this corpus — same honest pattern as Phases 2/4/7).

## Phase 10 — Action + Verification ✅ DONE

`financial_system/action/`: `models.py` (append-only `ActionAttempt`/
`ActionCase`) + `simulator.py` (policy-gated execution; the one file that
reads `recovery_labels.csv`'s `retry_would_succeed` — as a simulated
gateway response standing in for a real API, never as Recovery's own
decision logic, which never touches this file) + `loop.py` (the closed
loop). Recovery's RETRY is the flagship demonstration since it's the one
decision with genuine per-instance uncertainty (`decision_score` is always a
category base rate, never a per-instance guarantee).

**Done check result:** all 5 required cases pass on real payments, not
synthetic stand-ins — including case 4/5's `pay_66cebb42f9`: attempt 1
executes `RETRY_PAYMENT`, the simulated gateway reports `FAILURE`, the loop
deterministically escalates (never repeats the same action), attempt 1's
original record stays untouched in the append-only chain. Full batch over
all 160 failed payments (zero LLM cost): `{RESOLVED: 68, REVIEW: 57,
ESCALATE: 35}`, `19` cases needed a genuine second attempt. Every number
cross-validates exactly against Phase 7's own report (`REVIEW`=57 is exactly
insufficient_funds(35)+issuer_declined(22); `ESCALATE`=35 is exactly 16
one-attempt non-recoverable-category cases + 19 real escalations after a
failed retry) — independent confirmation the two phases agree.

## Phase 11 — Demo assembly

`ARCHITECTURE.md`'s 3-payment narrative, run against the real pipeline (not
scripted output), plus the metrics table from `PRD.md` §Success metrics.

**Done check:** a cold run (fresh process, same seed) reproduces the same
metrics — nothing about the demo depends on a lucky prior run's state.
