# Future Discovery.AI issue: generalize the retriever/evidence contract for bounded structured retrieval

**Status: documented, not filed, not implemented.** Deliberately shelved until after
the financial system's 610-settlement Phase 4 benchmark and the Controller/Risk/
Recovery phases are built — see `ARCHITECTURE.md`. Not a today problem: the
adapter-side fix below fully resolves the immediate issue with zero Discovery.AI
changes. This file exists so the architectural insight isn't lost, and is ready to
paste into a GitHub issue on `TheNova6000/Discovery.AI` when it's actually time to
work on it.

## Problem

Discovery.AI's evidence engine (`backend/evidence/engine.py`) supports
`max_results_per_retriever`, but `GroundAgent`'s own call site
(`backend/agents/ground_agent.py:260`, `gather_evidence(self.question)`) never
passes a `retrievers` override at all — every existing retriever is a ranked
external search engine (web/paper/book/video), and the abstraction implicitly
assumes that shape throughout: a retriever "searches," gets back up to N ranked
external resources, and each becomes a `synthesize_claim()` LLM call.

A retriever backed by a structured world model (a knowledge graph, in our case a
financial reconciliation graph) doesn't search — it traverses a bounded
neighborhood of already-known facts around a specific, already-identified subject.
Before our own fix, `FinancialStateRetriever.search()` returned that entire
neighborhood regardless of `max_results`, because nothing in the contract
distinguished "how many results the caller wants" from "how much evidence
actually exists."

**Measured impact, from this integration's own Phase 4 batch runs:** average
neighborhood size was 4.8 facts per investigation (max observed: 18, for a
multi-payment settlement), each triggering its own `synthesize_claim()` call
before the fix — multiple times more LLM calls per investigation than
`max_results_per_retriever=2` was meant to bound.

## Why this is an abstraction issue, not a finance-specific bug

We fixed our side entirely in the adapter (`FinancialStateRetriever` now ranks by
relevance — amount-proximity to the investigation's computed gap, then relation
type — and truncates to `max_results` itself, verified: avg 2.0 resources used vs.
4.8 offered, ranking still points at the most relevant facts). That's a complete,
correct fix for this integration.

But the same pattern would recur for any future structured/domain retriever
(an enterprise knowledge graph, an application database, a scientific graph):
each would have to independently reimplement "rank and truncate to max_results
myself," because the contract gives a retriever no standard way to say "here's
what I found, here's what I'm returning, here's what got left out."

## Proposed direction (not designed in detail — a starting shape)

A richer return type retrievers can optionally use instead of a bare
`list[RetrievedResource]`:

```python
EvidenceResult(
    items=[...],          # what's actually returned to the evidence engine
    total_available=18,   # optional: how many relevant items existed, when known
    returned=6,
    truncated=True,
    ranking="financial_relevance",  # optional: how the retriever prioritized
)
```

Key semantic distinction to preserve: **retrieval limit vs. evidence
completeness are different concepts.** 18 facts existing and 6 being returned
must not automatically mean "insufficient evidence" — a well-ranked 6 can fully
explain a question a poorly-ranked 18 wouldn't. Discovery.AI's evidence engine
should carry `truncated` as metadata, never interpret it as an investigation
outcome on its own.

## Non-goals

Discovery.AI should not gain financial arithmetic, reconciliation logic, fraud
scoring, or any domain-specific ranking — that stays in each adapter (our
`FinancialStateRetriever`'s ranking logic is finance-specific and correctly lives
in `financial_system/discovery_adapter/`, not in Discovery.AI). Discovery.AI's
job is only to respect whatever bound/ranking a retriever provides.

## Backward compatibility requirement

Existing retrievers (Tavily, Wikipedia, arXiv, Semantic Scholar, Open Library,
YouTube) return plain `list[RetrievedResource]` today and must keep working
unchanged — any new contract needs to accept both shapes, not force a rewrite of
every existing retriever to adopt this.

## When to actually do this

After the 610-settlement Phase 4 benchmark is a clean result on the *current*,
unmodified Discovery.AI, and after Controller/Risk/Recovery are built on top of
the working adapter. At that point: inspect `backend/evidence/engine.py`, the
`Retriever` base class, every existing retriever, and `GroundAgent`'s call flow
together (not from this document alone), design the smallest change that
generalizes without breaking anything, add tests for both the bounded-structured
and existing-list cases, run Discovery.AI's own test suite, and only then update
`FinancialStateRetriever` to use the new contract.
