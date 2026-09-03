"""
FinancialStateRetriever: the one place a financial fact crosses into
Discovery.AI's evidence pipeline.

Bound to ONE entity at construction time -- not a general-purpose search
retriever. discovery_adapter (never GroundAgent's own hardcoded
DEFAULT_RETRIEVERS list, which this project deliberately does not touch --
see investigate.py's module docstring) constructs a fresh instance per
investigation and passes it directly to gather_evidence(retrievers=[...]).
Because we control that call site, `search()` can ignore the free-text
`query` Discovery.AI would normally pass a web retriever: the investigation's
subject is already known structurally, so this degenerates from "search the
web" to "fetch this entity's evidence neighborhood."

Takes a `neighborhood_fn` (graph -> list[dict]) rather than being hardwired to
reconciliation_neighborhood() -- Phase 6 (risk/) is a second real caller, with
a differently-shaped subject (a device, not a settlement/payment) and its own
risk_neighborhood() query. One retriever class, the neighborhood-fetching
logic stays owned by whichever domain module needs it.

`max_results` IS honored (fixed after the 40-case batch showed evidence
neighborhoods up to 18 facts were all being sent regardless of Discovery.AI's
own max_results_per_retriever=2 default -- a real, uncapped LLM-call-volume
driver). Ranking, not arbitrary truncation: a fact whose amount is close to
the investigation's reference_amount (4A's computed unexplained gap) ranks
highest -- it's the strongest candidate explanation, and the most falsifiable.
The settlement's own `self` fact ranks lowest deliberately: its numbers are
already stated in the anchored question text (investigate.py's _run_4b), so
repeating it as a resource wastes a scarce slot that a real candidate
explanation (a fee, refund, or duplicate line item) could use instead.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable

from financial_system.discovery_adapter._vendor import ensure_on_path

ensure_on_path()

from backend.evidence.models import RetrievedResource  # noqa: E402
from backend.evidence.retrievers.base import Retriever  # noqa: E402

from financial_system.financial_graph.repository import GraphRepository  # noqa: E402

_RELATION_BASE_SCORE = {
    "deposited_as": 70,   # the actual-side anchor
    "generates": 55,      # fee -- a real candidate deduction
    "refunded_by": 55,    # refund -- a real candidate deduction
    "contains": 40,       # sibling payments in the same settlement
    "settles_into": 40,
    "self": 10,           # already stated in the question text -- lowest priority
}
_AMOUNT_MATCH_WEIGHT = 100.0  # amount-proximity dominates ranking -- it's the
                              # most falsifiable signal, per the priority order.


def _relation_base(relation: str) -> str:
    return relation.split(" ")[0]


def _score(fact: dict, reference_amount: Decimal | None) -> float:
    base = _RELATION_BASE_SCORE.get(_relation_base(fact["relation_from_subject"]), 30)
    amount = fact.get("amount")
    if reference_amount is None or amount is None:
        return base
    denom = max(abs(reference_amount), Decimal("1"))
    closeness = max(Decimal("0"), Decimal("1") - abs(amount - reference_amount) / denom)
    return base + float(closeness) * _AMOUNT_MATCH_WEIGHT


class FinancialStateRetriever(Retriever):
    source_type = "financial_state"

    def __init__(self, graph: GraphRepository, neighborhood_fn: Callable[[GraphRepository], list[dict]],
                 reference_amount: Decimal | None = None):
        self._graph = graph
        self._neighborhood_fn = neighborhood_fn
        self._reference_amount = reference_amount

    async def search(self, query: str, max_results: int = 3) -> list[RetrievedResource]:
        facts = self._neighborhood_fn(self._graph)
        ranked = sorted(facts, key=lambda f: _score(f, self._reference_amount), reverse=True)
        selected = ranked[:max_results] if max_results else ranked
        return [
            RetrievedResource(
                title=f"{fact['node_type']} {fact['node_id']} ({fact['relation_from_subject']})",
                url=f"financial-state://{fact['node_type'].lower()}/{fact['node_id']}",
                snippet=fact["summary"],
                source_type=self.source_type,
            )
            for fact in selected
        ]
