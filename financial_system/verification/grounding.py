"""
Verification check #3 -- Evidence grounding (NORTH_STAR.md Section 24:
"Was the reasoning grounded?" / Section 35: "grounding").

Exactly `financial_graph/queries.py::check_no_fabricated_relationships`'s
own structural idea ("every edge's endpoints must be real nodes in this
same graph"), applied one layer up: every `AgentVerdict.evidence` entry
and `affected_entities` entry must resolve to a real node in the SAME
graph the verdict was produced against. A dangling id here would mean an
agent's reason cites, or an action targets, something that doesn't
actually exist -- fabricated evidence, structurally, not by convention.

Deliberately NOT checking edge existence between the verdict's subject and
its evidence (e.g. "is there a path from Settlement X to node Y") --
`financial_graph/queries.py` already owns graph-structural integrity
(fabricated relationships, orphaned relationships, provenance coverage);
this check only owns the one thing that's new at the verdict layer: does
the id an agent WROTE DOWN actually resolve to something real. Scope
matches the task's four bounded checks -- no more.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from financial_system.financial_graph.repository import GraphRepository
from financial_system.verdict import AgentVerdict


@dataclass
class GroundingResult:
    agent: str
    n_verdicts: int
    n_evidence_checked: int
    n_evidence_missing: int
    n_affected_checked: int
    n_affected_missing: int
    missing: list[tuple[str, str, str]] = field(default_factory=list)  # (verdict.subject, field, missing_id)

    @property
    def passed(self) -> bool:
        return self.n_evidence_missing == 0 and self.n_affected_missing == 0


def check_evidence_grounding(graph: GraphRepository, verdicts: list[AgentVerdict]) -> GroundingResult:
    n_evidence_checked = n_evidence_missing = 0
    n_affected_checked = n_affected_missing = 0
    missing: list[tuple[str, str, str]] = []
    agent = verdicts[0].agent if verdicts else "?"

    for v in verdicts:
        for eid in v.evidence:
            n_evidence_checked += 1
            if not graph.node_exists(eid):
                n_evidence_missing += 1
                missing.append((v.subject, "evidence", eid))
        for aid in v.affected_entities:
            n_affected_checked += 1
            if not graph.node_exists(aid):
                n_affected_missing += 1
                missing.append((v.subject, "affected_entities", aid))

    return GroundingResult(
        agent=agent, n_verdicts=len(verdicts),
        n_evidence_checked=n_evidence_checked, n_evidence_missing=n_evidence_missing,
        n_affected_checked=n_affected_checked, n_affected_missing=n_affected_missing,
        missing=missing,
    )
