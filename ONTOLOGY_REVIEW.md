# Ontology Review — the fundamental objects, as actually implemented

Written at the user's request, after `ARCHITECTURE_REVIEW.md`, to answer one
question strictly: **what are the fundamental objects in this system, as
built — not as designed?** Every claim below is verified against the code
in this session (grep output, file:line), not recalled from the design
docs. Thirteen candidate objects, each checked against: what it is, who
creates/modifies it, whether it's immutable, what evidence supports it, its
relationship to world state, whether an LLM can touch it, and what happens
to it when the process exits.

Answers that are **identical across almost every object** are stated once
here rather than repeated thirteen times: nothing in this system is ever
modified after construction (every object is a pydantic model or dataclass,
built once, read thereafter — no `update_*` method exists anywhere except
on the raw ingestion layer, and even there only as insert-once); nothing
persists past the Python process that created it **except** `financial_state.db`
and `financial_graph.db` as files (and even those are deleted and rebuilt
from scratch on every run — confirmed: both `financial_state/builder.py:78-79`
and `financial_graph/builder.py`'s `build_graph()` unlink their db file
before rebuilding). The interesting answers are the exceptions to this, and
where an LLM can and can't reach.

## The thirteen objects

**1. Entity** (`GraphNode`, `financial_graph/models.py`) — one of 10 types
(Merchant, Customer, Device, PaymentInstrument, Order, Payment, Settlement,
BankTransaction, Refund, Fee). Created once by `_build_nodes()`, reading
`financial_state` rows directly — zero LLM involvement. **Provenance gap
found while verifying this**: `_node()`'s default is
`source_record_ids=[node_id]` (`builder.py:41-43`), and every call site in
`_build_nodes()` uses that default — so an Entity's `source_record_ids`
field is just its own id restated, not a link back to Phase 1's actual
provenance triple (`source_file`/`row_number`/`ingestion_run_id`). The
richer provenance exists one layer down (in `financial_state`) but doesn't
carry forward onto the graph node itself.

**2. Event** — **does not exist as an object.** Verified: there is no
`Event` class anywhere in the codebase. `orchestrator/events.py::classify_event_types()`
returns bare strings (`"PAYMENT_FAILED"`), computed fresh every call by
querying an Entity's *current* property (`payment.properties.get("status")
== "failed"`). This is a state predicate evaluated at query time, not a
recorded occurrence with its own timestamp and identity. This is the root
cause of `ARCHITECTURE_REVIEW.md`'s central finding: you cannot write a new
fact back into an event log that was never built.

**3. State** (`financial_state.db` + `financial_graph.db`) — genuinely
immutable by design, and correctly so at the ledger layer (Phase 1's own
invariant: every source record ingested exactly once, never updated). The
gap: this immutability is being asked to serve **two** roles that need to
be different — "the historical record of what was originally generated"
(correctly immutable) and "the current status of the world" (which needs
to be mutable, or at least layered on top of an event history). We only
built the first role. There is no `update_payment_status()` anywhere, and
there structurally can't be one without breaking Phase 1's own append-only
invariant — which means adding one requires a genuine design decision, not
a quick patch.

**4. Observation** — **conflated with Inference.** No function separates
"here is what I looked at" from "here is what I concluded from it."
`reconcile_settlement()`, `compute_device_risk_signals()`, and
`compute_recovery_signals()` all read graph state *and* compute the
interpreted signal in the same pass, returning one dataclass that mixes raw
traversal results with derived numbers (e.g. `RiskSignals.max_burst_count`
is already an interpretation, not a raw reading).

**5. Evidence** — **means two different things depending on the layer**,
verified as a real naming collision, not just an academic distinction. Ours
(`AgentVerdict.evidence`, `InvestigationResult.evidence`): `list[str]` of
entity ids — a provenance pointer. Discovery.AI's own (`Claim.evidence` in
`vendor/discovery-ai/backend/evidence/models.py`): a single text string —
an extracted answer. These never get reconciled: confirmed by grep, `_run_4b`
never reassigns `result.evidence` after `_deterministic_pass` sets it, so
even a real 4B investigation doesn't add whatever new entities Discovery.AI
actually found relevant — the evidence list stays exactly what 4A's
deterministic pass already computed.

**6. Investigation** (`InvestigationResult`) — the **one object with
genuinely correct FACT/INFERENCE/HYPOTHESIS separation**, and the one place
in the entire system an LLM directly authors content (`narrative`,
`hypotheses`, `inferences`, `investigation_confidence`). Verified precisely
what `_run_4b` touches versus never touches: it sets exactly `narrative`,
`investigation_confidence`, `inferences`, `hypotheses`,
`ground_decision_action`, `executed_4b`, and the `llm_*` metrics fields —
`status`, `expected_amount`, `actual_amount`, `unexplained_amount`,
`facts`, and `evidence` are all set by 4A before the LLM ever runs and never
touched afterward. This is the cleanest-drawn LLM boundary in the codebase
and the model the other objects should have followed. Persistence is
inconsistent, though: `batch_4b.py` persists every `InvestigationResult` to
JSONL; `Controller`/`Risk`/`Recovery`'s calls via `investigate_evidence()`
build one, copy its `narrative` into `AgentVerdict.reason`, and discard the
rest.

**7. Finding** — **not a unified object; three independent, structurally
identical dataclasses.** `ReconciliationFact` (`reconciliation/deterministic.py`),
`RiskSignals` (`risk/signals.py`), `RecoverySignals` (`recovery/signals.py`)
all play the exact same ontological role — "the deterministic facts one
agent computed before deciding" — with different field names and no shared
base type. This is the clearest concrete candidate for unification if the
ontology gets revised: these three are secretly the same object.

**8. Verdict** (`AgentVerdict`) — **the one object that successfully
unified across all three domain agents**, real evidence the "common
decision language" design worked. Built fresh on every call (`_to_verdict()`
in each of `controller.py`/`risk_agent.py`/`recovery_agent.py`), never
cached or looked up by id — which is the direct cause of finding #3 below.
`reason` is the one field an investigation can silently overwrite,
collapsing the FACT/INFERENCE/HYPOTHESIS distinction Investigation carefully
preserved into one flat string. `decision`/`decision_score`/`proposed_action`
are never touched by an LLM anywhere — confirmed structurally, not just by
convention.

**9. Policy Decision** (`PolicyDecision`) — the one object with an
**explicit, structural** LLM boundary: it has no `investigation_confidence`
field at all, not filtered out, absent. Minor provenance gap found: it
carries `subject` (one id) forward from the verdict but not the verdict's
full `evidence` list, so a `PolicyDecision` alone can't be traced back to
every entity its underlying decision rested on without re-fetching the
original verdict.

**10. Action** — **just a string**, confirmed (`"RETRY_PAYMENT"`,
`"HOLD_PAYMENT"`, `"NONE"`, etc.), with no independent identity: no
`action_id`, no timestamp, no recorded precondition. Lives only inside
`ActionAttempt.action_taken`. `execute_action()` never mutates any world
state — it returns a boolean and a log string. This is where the central
finding bites structurally: even a "successfully executed" action has no
durable effect on `financial_state`/the graph, by construction, not by bug.

**11. Outcome** — not a distinct object either; represented as
`ActionAttempt.verification_result: Optional[str]` (`"SUCCESS"` /
`"FAILURE"` / `None`). `verify_retry()` is the **one and only** place in
the entire action/verification pipeline that reads
`ground_truth/recovery_labels.csv` — confirmed by design and by grep — a
deliberate, documented gateway simulation, never read by any agent's actual
decision logic. In the user's own worked example ("NEW FACT: retry attempt
failed"), that new fact has no data model to live in beyond this one
optional string field on a never-persisted attempt record.

**12. Verification** — **conflated with Outcome.** `verify_retry()` returns
the check and its result as one tuple; there's no object representing "a
verification was attempted" independent of what it found. This also means
there's no way to represent "pending" as a distinct state from "not
applicable" — both currently collapse to `None`.

**13. Case** — **three independent, non-unified case-like objects**,
confirmed by grep to share no id space and never reference each other:
`CompoundCase` (Controller+Risk+Recovery merge, `orchestrator/`),
`ActionCase` (the retry/verify/escalate chain, `action/`, Recovery-subject
only — confirmed `run_action_loop()` hardcodes a call to
`run_recovery_for_payment()`, never generalized to Controller or Risk), and
arguably `InvestigationResult` itself (a case for one question). Each gets
computed fresh from scratch on every call — this is the direct mechanism
behind the "duplicate verdict generation" finding: `orchestrator.py` and
`action/loop.py` each independently call `run_recovery_for_payment()` for
the same payment, because neither has anywhere to look up "has this already
been decided."

## Synthesis: what actually happened as this got built

Reading across all thirteen at once, one pattern explains almost every gap
above: **this system was built by threading one decision-shaped concept
(Verdict) consistently through every phase, without ever building the
event/history layer underneath it.** Verdict succeeded precisely because
each phase's author (this session) kept asking "what does Controller/Risk/
Recovery decide, and how does Policy gate it" — a decision-centric question
— and never had to ask "what happened, when, and what's the current state
of the world as a result" until Phase 10 forced the question. The three
un-unified Finding types, the missing Event object, and the conflated
Observation/Inference step are all downstream of the same thing: the system
has a rich, correct model of **reasoning about a snapshot**, and no model
at all of **time**.

That's not a scattered set of four bugs. It's one honest gap, showing up in
five different places because it's structural: this codebase has never had
to represent "before" and "after."

## The one thing worth stating plainly

Across all thirteen objects, an LLM can only ever touch four fields on one
object: `InvestigationResult.narrative`, `.inferences`, `.hypotheses`, and
`.investigation_confidence`. Everything else — every Entity, every State
table, every Finding, every `Verdict.decision`/`decision_score`, every
`PolicyDecision`, every `Action`, every `Outcome` — is verified, by
structure and by grep, never to have an LLM anywhere near it. That boundary
is real. It's the one part of this ontology that doesn't need revising.
