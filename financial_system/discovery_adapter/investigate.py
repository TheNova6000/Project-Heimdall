"""
open_investigation(): the one function every domain agent calls to ask
Discovery.AI "why." Two passes:

  4A (always runs, zero LLM): gathers the same evidence neighborhood the
  retriever exposes and does the arithmetic -- Discovery.AI's LLM must never
  be trusted with the actual numbers (explicit design decision). The only
  case-general deterministic explanation this looks for is an exact
  duplicate line item (a payment counted twice under a settlement's
  `contains` edges) -- standard reconciliation technique, not overfit to any
  one anomaly's mechanics.

  4B (only when has_any_provider_key() is True): calls Discovery.AI's real
  decide_next_step / gather_evidence(retrievers=[FinancialStateRetriever]) /
  synthesize_answer -- unmodified Discovery.AI code, GroundAgent's own class
  never instantiated (see module docstring rationale: GroundAgent hardcodes
  DEFAULT_RETRIEVERS with no override, so reusing it would mean either
  patching Discovery.AI's source or silently getting web retrievers on
  financial questions -- neither acceptable). decide_next_step's decision is
  logged into the result, never acted on (no recursive decomposition in
  Phase 4 -- "one exception, one investigation, one explanation").
  Discovery.AI's narrative/confidence are attached to the result but never
  override 4A's status or unexplained_amount.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

from financial_system.discovery_adapter._vendor import ensure_on_path
from financial_system.discovery_adapter.models import InvestigationRequest, InvestigationResult, InvestigationStatus
from financial_system.financial_graph.queries import reconciliation_neighborhood, risk_neighborhood
from financial_system.financial_graph.repository import GraphRepository
from financial_system.reconciliation.deterministic import reconcile_settlement


def _neighborhood_fn_for(request: InvestigationRequest):
    """Dispatches which evidence neighborhood an investigation's subject gets
    -- reconciliation_neighborhood() for Settlement/Payment (Phase 4/5),
    risk_neighborhood() for Device (Phase 6). New subject types add a case
    here, not a new retriever class (financial_state_retriever.py's own
    docstring)."""
    if request.subject_type == "Device":
        return lambda g: risk_neighborhood(g, request.subject_id)
    return lambda g: reconciliation_neighborhood(g, request.subject_type, request.subject_id)


def _deterministic_pass(graph: GraphRepository, request: InvestigationRequest) -> InvestigationResult:
    """Standalone convenience only -- Controller (Phase 5) calls
    reconcile_settlement() directly and never goes through this. Kept here so
    open_investigation() stays a complete, self-sufficient one-call demo path
    for smoke_test.py/batch_4b.py."""
    if request.subject_type != "Settlement":
        facts = reconciliation_neighborhood(graph, request.subject_type, request.subject_id)
        return InvestigationResult(
            request=request, status=InvestigationStatus.UNEXPLAINED,
            facts=[f["summary"] for f in facts], evidence=[f["node_id"] for f in facts],
            execution_note="4A's deterministic reconciliation pass only supports "
                            "Settlement subjects right now",
        )

    fact = reconcile_settlement(graph, request.subject_id)
    return InvestigationResult(
        request=request, status=InvestigationStatus(fact.status),
        expected_amount=str(fact.expected_amount) if fact.expected_amount is not None else None,
        actual_amount=str(fact.actual_amount) if fact.actual_amount is not None else None,
        unexplained_amount=str(fact.unexplained_amount) if fact.unexplained_amount is not None else None,
        facts=fact.facts, evidence=fact.evidence, execution_note=fact.note,
    )


async def _run_4b(graph: GraphRepository, request: InvestigationRequest, result: InvestigationResult) -> InvestigationResult:
    ensure_on_path()
    from backend.evidence.engine import DEFAULT_MAX_RESULTS_PER_RETRIEVER, gather_evidence
    from backend.questions.decision import decide_next_step
    from backend.questions.exceptions import QuestionEngineError
    from backend.questions.models import Question, QuestionLevel
    from backend.questions.synthesis import synthesize_answer

    from financial_system.discovery_adapter.call_metrics import capture_call_metrics
    from financial_system.discovery_adapter.financial_state_retriever import FinancialStateRetriever

    neighborhood_fn = _neighborhood_fn_for(request)
    reference_amount = Decimal(result.unexplained_amount) if result.unexplained_amount is not None else None
    offered = neighborhood_fn(graph)
    result.resources_offered = len(offered)
    result.resources_used = min(len(offered), DEFAULT_MAX_RESULTS_PER_RETRIEVER)

    # Anchored to 4A's actual computed gap, not left open-ended -- the smoke test
    # showed an unanchored "why do these differ" question lets the LLM pattern-match
    # onto the first fee/tax fact it sees and call it the cause even when the
    # number is off by 29x (a 0.75-confidence explanation for a real gap of
    # 456.92 that cited a 15.74 fee). Naming the exact unexplained amount turns
    # this into a falsifiable check -- "does X account for THIS number" -- instead
    # of free association. Still never lets the narrative override result.status
    # below; this only makes the narrative itself more honest.
    anchored_text = request.question_text
    if result.unexplained_amount is not None:
        anchored_text += (
            f" A deterministic reconciliation pass already computed: expected={result.expected_amount}, "
            f"actual={result.actual_amount}, unexplained_amount={result.unexplained_amount} "
            f"(after accounting for any exact-duplicate line items already found). Only treat a resource "
            f"as explaining this gap if its amount numerically accounts for approximately "
            f"{result.unexplained_amount} -- do not cite a fee, tax, or deduction that does not "
            f"actually match this specific figure."
        )

    question = Question(
        text=anchored_text,
        rationale="Opened by the financial system's Controller to explain a reconciliation exception.",
        dimension_id="financial_reconciliation",
        level=QuestionLevel.GROUND,
        entity_name=f"{request.subject_type}:{request.subject_id}",
        abstraction_name="Financial Reconciliation",
    )

    try:
        with capture_call_metrics() as cm:
            decision = await decide_next_step(question)
            result.ground_decision_action = decision.action

            claims = await gather_evidence(
                question, retrievers=[FinancialStateRetriever(graph, neighborhood_fn, reference_amount)]
            )
            result.hypotheses = [
                f"{c.evidence} (confidence={c.confidence:.2f}, source={c.source.title})" for c in claims
            ]

            draft = await synthesize_answer(question, [c.evidence for c in claims])

        result.narrative = draft.answer
        result.investigation_confidence = draft.confidence
        result.inferences = [draft.answer]
        result.executed_4b = True
        result.llm_latency_seconds = cm.metrics.latency_seconds
        result.llm_fallback_events = cm.metrics.fallback_events
        result.llm_full_failures = cm.metrics.full_failures
        result.llm_providers_seen = cm.metrics.providers_seen
    except QuestionEngineError as e:
        result.execution_note = (result.execution_note + f" | 4B failed: {e}").strip(" |")
    return result


def _has_usable_key() -> bool:
    """Deliberately NOT Discovery.AI's own has_any_provider_key() -- that helper
    only checks the singular *_API_KEY env vars, while PROVIDER_KEY_POOLS (what
    structured_call() actually draws from) also reads the plural *_API_KEYS
    multi-account form. Setting only GROQ_API_KEYS (our multi-account setup)
    would make has_any_provider_key() wrongly report False. Fixed here, in our
    own code -- not a Discovery.AI edit."""
    ensure_on_path()
    from backend.questions.llm_config import PROVIDER_KEY_POOLS

    return any(PROVIDER_KEY_POOLS.values())


def open_investigation(request: InvestigationRequest, graph: GraphRepository) -> InvestigationResult:
    """Standalone, self-sufficient path: runs 4A itself, then 4B if warranted.
    Used by smoke_test.py/batch_4b.py for direct testing of the whole pipeline
    in one call. Controller (Phase 5) does NOT use this -- it already has 4A's
    facts from reconcile_settlement() and calls investigate_evidence() below,
    so a case 4A already resolves never triggers a wasted LLM call."""
    result = _deterministic_pass(graph, request)
    return investigate_evidence(request, result, graph)


def investigate_evidence(request: InvestigationRequest, result: InvestigationResult,
                          graph: GraphRepository) -> InvestigationResult:
    """The entry point Controller actually calls: `result` already carries 4A's
    status/expected/actual/unexplained/facts/evidence (from
    reconcile_settlement()) -- this only runs 4B against it, gated on
    _has_usable_key(). Never recomputes 4A, never called for a case Controller
    has already resolved on its own."""
    if _has_usable_key():
        result = asyncio.run(_run_4b(graph, request, result))
    else:
        result.execution_note = (
            result.execution_note + " | 4B not executed: no LLM provider key configured"
        ).strip(" |")

    return result
