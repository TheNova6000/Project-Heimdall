# Rules — boundaries for anyone (human or AI) building this

## The one rule everything else follows from

Every piece of logic is exactly one of the four kinds of intelligence in
`ARCHITECTURE.md` §0 (deterministic / graph / investigative / operational).
**Only investigative-intelligence code may call an LLM**, and that code lives
in exactly one place: `discovery_adapter/`. If you're about to add an LLM call
inside `risk/`, `reconciliation/`, `recovery/`, `policy/`, or the orchestrator,
stop — that logic belongs in deterministic/graph intelligence instead, or the
LLM call belongs behind `discovery_adapter.open_investigation()`.

## Discovery.AI boundary

- `discovery_adapter/` is the **only** module in `financial_system/` allowed to
  import from Discovery.AI's `backend/*`.
- Don't fork or hand-edit Discovery.AI's internals. The one sanctioned exception
  is additive: extending `backend/questions/relation_types.py` with the
  `FINANCIAL` relation family (documented in `ARCHITECTURE.md` §1.2) — additive
  only, never renaming or removing existing types other domains may depend on.
- Don't attempt to implement the View/Projection layer to get "multiple lenses
  on one graph." Use direct Cypher filtered by relation family instead
  (`ARCHITECTURE.md` §3). If that stops being sufficient, that's a conversation,
  not a silent workaround.

## Money handling

- Never use `float` for a monetary value that gets compared, summed, or matched
  against another monetary value in real logic (`reconciliation/`, `fees/`,
  matching code). Use `Decimal` or integer paise. Floats are only acceptable in
  `data_generator/` (synthetic test data, not logic under test) — comparisons
  against generated amounts elsewhere must still go through the real
  reconciliation code path, not re-derive expected values with floats.
- A reconciliation "match" always states its tolerance explicitly (e.g. `<= ₹1`
  is auto-resolved per the Policy Engine rule in `ARCHITECTURE.md` §6) — never
  an implicit epsilon buried in a comparison.

## Stack

- Python 3.11, matching Discovery.AI. Reuse its Neo4j driver
  (`backend/graph/driver.py`) via the adapter rather than opening a second
  connection with different settings.
- Prefer the standard library. Don't add a dependency (pandas, a new ORM, a new
  LLM SDK) unless the stdlib approach has actually become the bottleneck —
  `data_generator/generate_dataset.py` is the model: csv/json/uuid/datetime only.
- Pydantic for every cross-module contract (`AgentVerdict`, `PolicyRule`,
  `VerificationResult`) — these are read by multiple modules and need real
  validation, not duck-typed dicts.

## Error handling

- No silent skips. A row `ingestion/` can't parse goes to an explicit rejects
  log with a reason, never dropped quietly.
- Every `PolicyDecision` (ALLOW/REVIEW/DENY) carries the rule id that produced
  it — "REVIEW" with no traceable rule is a bug.
- A `VerificationResult` of `FAILURE` must re-enter the investigation protocol
  (`ARCHITECTURE.md` §7) — it may not just get logged and dropped.

## Actions

- **Nothing in this project calls a real payment, refund, or bank API.** Action
  execution (`actions/`) simulates and logs; this is a hard rule for buildathon
  scope, not a TODO.
- Track 2 is explicitly "strictly defense-only: anything offense-capable is
  disqualified" — nothing built here may be repurposed to execute fraud, only to
  detect/explain/block it.

## Claims about the system

- Never report a metric (precision, recall, match rate, recovery rate) that
  wasn't actually computed against the held-out `data/ground_truth/` files. "It
  looked right in the demo" is not a metric.
- `data/ground_truth/` is read only by scoring code and the demo script — if
  any agent's actual decision logic reads from it, that agent is cheating on
  its own eval and any reported metric is void.

## Style

- No comments explaining *what* code does — names should do that. A comment is
  only for a non-obvious *why* (a workaround, a subtle invariant).
- No speculative abstraction — build the concrete case in front of you; three
  similar agent modules is fine, a generic `BaseAgent` framework before a third
  agent exists is not.
