# Financial Agentic Operating System — Architecture v0.2

Discovery.AI is a dependency, not a fork. This repo (`financial_system/`) owns everything
below; `discovery_adapter/` is the only module that imports Discovery.AI code.

Risk, Controller, and Recovery are specialized reasoning domains inside one system, not
three separate agents bolted together. They share one world model, one investigation
substrate (Discovery.AI), one verdict contract, and one policy gate.

## 0. Four kinds of intelligence

Every piece of reasoning in this system is exactly one of these — mixing them is the
main way this kind of project turns into an unaccountable black box, so each layer below
states which kind it is.

| # | Kind | Question | LLM involved? |
|---|---|---|---|
| 1 | Deterministic | What objectively happened? (amount diffs, counts, timestamps) | No |
| 2 | Graph | What is connected to what? | No — Cypher over typed relations |
| 3 | Investigative | Why? | Yes — Discovery.AI, via `discovery_adapter` only |
| 4 | Operational | What should we do? | No — policy rules over a verdict |

Any agent code that reaches for an LLM to answer a (1), (2), or (4)-shaped question is
a bug in the design, not a modeling choice.

```
financial_system/
├── ingestion/            # CSV/API → normalized events
├── financial_state/      # normalized records (source of truth)
├── entity_resolution/     # deterministic + probabilistic + agentic matching
├── financial_graph/        # writes to Discovery.AI's Neo4j, financial relation types
├── discovery_adapter/      # the ONLY module that touches backend/* of Discovery.AI
├── reconciliation/         # Controller Agent
├── risk/                   # Risk Agent (Velocity/Network/Behavior sub-agents)
├── recovery/                # Recovery Agent
├── policy/                  # Policy Engine
├── actions/                  # Action execution (simulated for demo)
└── verification/              # closes the loop
```

---

## 1. Financial Event Model

### 1.1 Entities → Neo4j `Node` (name, scope)

Scope disambiguates instances the way Discovery.AI already scopes topic entities
(`electric grid` vs `telecom`). Here scope = `dataset_run_id` or `merchant_id`, so a
demo re-run doesn't collide with a previous one in the same graph.

```
Merchant, Customer, Payment, Order, Authorization, Capture, Refund,
Settlement, Payout, BankTransaction, Fee, Tax, Chargeback, Dispute,
Device, IP, PaymentInstrument, Account
```

### 1.2 Relations → extend `backend/questions/relation_types.py`

This file is already documented as the single source of truth other modules read
from. Add a `FINANCIAL` family block to it (additive, doesn't touch the existing
6 families/35 types):

| New type | Family | Meaning |
|---|---|---|
| `initiated` | INTERACTION | Customer → Payment |
| `belongs_to` | COMPOSITION | Payment → Order |
| `authorized_by` | DEPENDENCY | Payment → Authorization |
| `captured_as` | TEMPORAL | Payment → Capture |
| `generates` | CAUSAL | Payment → Fee/Tax |
| `refunded_by` | CAUSAL | Payment → Refund |
| `settles_into` | TEMPORAL | Payment → Settlement |
| `deducts` | COMPOSITION | Settlement → Fee |
| `deposited_as` | TEMPORAL | Settlement → BankTransaction |
| `matches` | CLASSIFICATION | cross-system identity link, carries `confidence` + `evidence[]` |
| `shares_device_with` / `shares_instrument_with` | INTERACTION | Risk graph edges |

Already-existing types you reuse as-is: `contains`, `is_part_of`, `causes`,
`enables`, `prevents`, `requires`, `depends_on`, `precedes`, `follows`,
`transfers_funds_to`, `authorizes`, `regulates`, `instance_of`.

`matches` is the important one — it's how Entity Resolution output gets stored,
and it's queryable/auditable the same way any other typed edge is.

---

## 2. Three-Layer Memory

| Layer | Storage | Owner | Mutable? |
|---|---|---|---|
| Raw data | CSV/API payloads as received | `ingestion/` | append-only |
| Financial State | normalized rows (SQLite or Postgres table per entity) | `financial_state/` | source of truth, corrections only |
| Knowledge Graph | Discovery.AI's Neo4j, financial `Node`s + relations above | `financial_graph/` via `discovery_adapter/` | append-only, `investigation_status` accumulates |

Agent *execution* state (what a Risk/Controller/Recovery agent has checked, retried,
escalated) is a **fourth**, separate store — mirrors Discovery.AI's own SQLite
`AgentState` checkpoint table, kept distinct from the Neo4j world model for the same
reason Discovery.AI keeps them distinct: investigation trace ≠ persisted fact.

---

## 3. `discovery_adapter/` — the actual integration surface

Two things live here, nothing else:

**a) `FinancialStateRetriever(BaseRetriever)`** — implements the interface in
`backend/evidence/retrievers/base.py`. Instead of hitting Tavily/arXiv/etc., it
queries `financial_state/` for records matching the investigation's entity
(payment_id, order_id, settlement_id...) and returns them as `RetrievedResource`
objects, so they flow into `Claim` the same way a web search result would. Registered
in `backend/evidence/engine.py`'s retriever list, gated to fire only when
`domain == "financial"`.

**b) `open_investigation(question, entity_id, scope) -> GroundResult`** — thin wrapper
around `GroundAgent(persist_to_graph=True, gather_evidence=True)`, pinned to use only
`FinancialStateRetriever`. This is the single call site every domain agent uses to ask
Discovery.AI "why" — Risk, Controller, and Recovery never construct a `GroundAgent`
directly, so the integration point stays in one file.

Reads (Risk Agent's network view, Controller's flow view) do **not** go through
`GroundAgent` at all — they're direct Cypher against the same Neo4j instance,
filtered by relation family:

```python
# risk/network_view.py
MATCH (c:Node)-[r]-(d:Node)
WHERE r.type IN INTERACTION_TYPES AND d.name = $device_id
RETURN c, r, d
```

This gets you "one graph, multiple lenses" for the demo without building the
unimplemented View/Projection layer.

---

## 4. Agent Contract

Every domain agent (Risk, Controller, Recovery) emits the same typed struct —
this is what the Decision Engine and Policy Engine consume, regardless of source:

```python
class AgentVerdict(BaseModel):
    agent: Literal["risk", "controller", "recovery"]
    subject: str                       # entity id: payment_id, exception_id...
    decision: str                      # e.g. REVIEW / EXCEPTION / RETRY
    reason: str                        # human-readable
    evidence: list[EvidenceRef]        # graph node/edge ids or Claim ids this rests on

    decision_score: float              # deterministic-intelligence (§0, kind 1) score —
                                        # the number policy rules gate on
    investigation_confidence: float | None   # Discovery.AI's synthesis confidence, kind 3 —
                                        # explains the verdict, never gates it

    proposed_action: str               # HOLD_PAYMENT / ESCALATE_TO_FINANCE / RETRY_PAYMENT...
    investigation_id: str | None       # set if an open_investigation() call backs this verdict
    metrics: dict[str, float]          # raw features the decision_score was computed from
    affected_entities: list[str]       # other entity ids this verdict implicates
```

`evidence` always points back into the graph/Claim store — a verdict with no
traceable evidence is a bug, not a valid output. This is what makes the demo's
"show the audit trail" bar (Track 1) and "honest metrics" bar (Track 2) the same
mechanism instead of two separate asks. `metrics` is what lets the UI print *why*
`decision_score` is 0.94 instead of asserting it.

### Epistemic status: FACT / INFERENCE / HYPOTHESIS

Nothing gets promoted to a canonical graph edge just because an LLM said it. Reuse
Discovery.AI's own provenance fields instead of inventing a parallel system:

| Status | Source | Discovery.AI mechanism |
|---|---|---|
| FACT | Financial State layer, written directly by ingestion | n/a — deterministic, not a Claim |
| INFERENCE | Graph/deterministic-intelligence agent output (e.g. "shared-device pattern") | `trace_claim` = `derived`/`synthesized` |
| HYPOTHESIS | Discovery.AI synthesis not yet backed by an investigated child | `audit_synthesis` = `uninvestigated` |

A HYPOTHESIS-tagged claim stays attached to its `Question` node, never becomes a
`matches`/`causes`/etc. edge on its own — an agent (or a human, via policy REVIEW)
has to act on it before anything derived from it is written back as fact.

### Financial Orchestrator (deterministic intelligence, kind 1 — no LLM)

A plain routing table, not another agent: `event_type → [agents to invoke]`.

```
PAYMENT_CREATED    → Risk, Controller(maybe)
PAYMENT_FAILED      → Recovery
SETTLEMENT_RECEIVED → Controller
```

Its second job is merging verdicts that share a `subject`/`affected_entities` into
a **Compound Case** before Policy sees them, and — when a compound case is opened —
firing one `open_investigation("investigate all relationships surrounding <id>")`
call instead of leaving each domain agent to investigate its own slice separately.

---

## 5. Investigation Protocol

1. A domain agent detects something worth explaining (reconciliation gap, device
   overlap, payment failure) using its own deterministic logic over the graph/state —
   **not** an LLM call.
2. It calls `discovery_adapter.open_investigation(question, entity_id, scope)`.
3. Discovery.AI's Ground Agent loop runs as-is: decide → decompose → gather
   (via `FinancialStateRetriever`) → synthesize → audit.
4. Result comes back as a `GroundResult` with claims + `investigation_status`.
5. The domain agent turns that into an `AgentVerdict` (§4), computing its own
   `confidence` and `decision`/`proposed_action` from the investigation's findings
   plus its own deterministic checks — never passes Discovery.AI's raw confidence
   through untouched.
6. If a verdict references entities another agent already flagged (§15 of your
   plan — compound investigations), the Decision Engine merges verdicts sharing an
   entity into one compound case before it reaches Policy.

---

## 6. Policy / Action Protocol

```python
class PolicyRule(BaseModel):
    id: str
    condition: str         # e.g. "risk_score > 0.90 and amount > 1000000"
    outcome: Literal["ALLOW", "REVIEW", "DENY"]
    action_if_allow: str | None

class PolicyEngine:
    def evaluate(self, verdict: AgentVerdict) -> PolicyDecision: ...
```

Rules are data (a table/YAML), not code — judges can read them, and you can show
the exact rule that fired for a given case in the demo. `ALLOW` executes
`proposed_action` immediately (simulated for the demo — log the action, don't call
a real payment API); `REVIEW` queues for a human-review view; `DENY` blocks and logs
why.

---

## 7. Verification Protocol

```python
class VerificationResult(BaseModel):
    action_id: str
    outcome: Literal["SUCCESS", "FAILURE"]
    detail: str

def verify(action_id: str) -> VerificationResult: ...
```

`FAILURE` re-enters step 2 of the Investigation Protocol with the verification
result as new evidence (`why did the retry fail?`) — this is the loop-closing part,
and it's also just another `open_investigation()` call, not new machinery.

---

## MVP phase mapping

| Phase | Module | Depends on |
|---|---|---|
| 1. Financial Event Graph | `ingestion/`, `financial_state/`, `entity_resolution/`, `financial_graph/` | nothing external |
| 2. Deterministic reconciliation | `reconciliation/` | Phase 1 |
| 3. Discovery.AI investigation | `discovery_adapter/` (both pieces in §3) | Phase 1, a running Discovery.AI instance |
| 4. Risk / Controller / Recovery agents | `risk/`, `reconciliation/`, `recovery/` | Phase 2–3 |
| 5. Policy Engine | `policy/` | Phase 4 (needs `AgentVerdict` shape) |
| 6. Action simulation | `actions/` | Phase 5 |
| 7. Verification | `verification/` | Phase 6 |

Build order should track this table — Phase 3 (the adapter) is the highest-risk
item since it's the only place touching Discovery.AI internals; get one
`open_investigation()` call working end-to-end on a single reconciliation exception
before building the three agents on top of it.
