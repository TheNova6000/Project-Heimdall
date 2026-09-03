"""
Phase 8 done check (Phases.md): confirm at least one compound case is created
from overlapping Risk+Controller verdicts on the same entity. Run across all
1000 payments (zero LLM cost, investigate=False) rather than asserting the
claim from a hand-picked example -- if overlapping cases exist in this
corpus, this finds them for real.

Also reports the CONTEMPORANEOUS conflict count (Block 5's temporal-honesty
fix, a993b20) alongside the original offline one -- both real, kept
distinct: the offline count includes conflicts only visible with
full-history hindsight on Risk's side; the contemporaneous count uses
risk_as_of=<payment's own created_at>, i.e. only conflicts where Risk's
disagreement was genuinely knowable at the moment the decision was made.

Run directly: `python -m financial_system.orchestrator.runner`
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.store import FinancialStateStore
from financial_system.orchestrator.orchestrator import process_payment

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DB = REPO_ROOT / "financial_system" / "data" / "financial_state.db"


def run(graph, payment_ids: list[str]) -> list:
    cases = []
    for i, pid in enumerate(payment_ids, 1):
        cases.append(process_payment(graph, pid, investigate=False))
        if i % 200 == 0 or i == len(payment_ids):
            print(f"  [{i}/{len(payment_ids)}]")
    return cases


def run_contemporaneous(graph, payment_ids: list[str]) -> list:
    cases = []
    for i, pid in enumerate(payment_ids, 1):
        payment = graph.get_node(pid)
        as_of = datetime.fromisoformat(payment.properties["created_at"])
        cases.append(process_payment(graph, pid, investigate=False, risk_as_of=as_of))
        if i % 200 == 0 or i == len(payment_ids):
            print(f"  [{i}/{len(payment_ids)}]")
    return cases


def print_report(cases: list) -> bool:
    total = len(cases)
    event_counts = Counter(e for c in cases for e in c.triggered_events)
    agent_counts = Counter(a for c in cases for a in c.invoked_agents)
    verdict_present = Counter()
    for c in cases:
        if c.controller_verdict:
            verdict_present["controller"] += 1
        if c.risk_verdict:
            verdict_present["risk"] += 1
        if c.recovery_verdict:
            verdict_present["recovery"] += 1

    multi_verdict = [c for c in cases if sum(v is not None for v in
                     (c.controller_verdict, c.risk_verdict, c.recovery_verdict)) >= 2]
    risk_and_controller = [c for c in cases if c.risk_verdict is not None and c.controller_verdict is not None]
    with_conflicts = [c for c in cases if c.conflicts]

    print(f"\n-- Phase 8 Orchestrator report ({total} payments) --")
    print(f"Event types triggered: {dict(event_counts)}")
    print(f"Agents invoked (routing decision, before subject-availability checks): {dict(agent_counts)}")
    print(f"Verdicts actually produced (agent invoked AND had a valid subject): {dict(verdict_present)}")
    print(f"\nCompound cases (>=2 verdicts present): {len(multi_verdict)}/{total}")
    print(f"Cases with BOTH Risk and Controller verdicts: {len(risk_and_controller)}")
    print(f"Cases with a detected conflict: {len(with_conflicts)}")

    if risk_and_controller:
        example = risk_and_controller[0]
        print(f"\nExample Risk+Controller compound case: {example.subject}")
        print(f"  controller: {example.controller_verdict.decision} ({example.controller_verdict.reason[:80]})")
        print(f"  risk:       {example.risk_verdict.decision} ({example.risk_verdict.reason[:80]})")
        print(f"  shared_entities: {example.shared_entities}")

    if with_conflicts:
        print(f"\nExample conflict: {with_conflicts[0].subject}")
        for c in with_conflicts[0].conflicts:
            print(f"  - {c}")

    return len(risk_and_controller) >= 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Building graph...")
    state, graph = build_graph()

    payment_ids = [r["payment_id"] for r in state.all_rows("payments")]
    print(f"Running Orchestrator over {len(payment_ids)} payments...")
    cases = run(graph, payment_ids)

    passed = print_report(cases)

    print("\n-- Contemporaneous conflicts (Block 5 temporal-honesty fix) --")
    contemporaneous_cases = run_contemporaneous(graph, payment_ids)
    n_contemporaneous = sum(1 for c in contemporaneous_cases if c.conflicts)
    n_offline = sum(1 for c in cases if c.conflicts)
    print(f"Offline (full-history) conflicts: {n_offline}/{len(payment_ids)}")
    print(f"Contemporaneous (decision-time-honest) conflicts: {n_contemporaneous}/{len(payment_ids)}")
    print("Both real, kept distinct -- see this file's own module docstring.")

    print("\nPHASE 8: PASS" if passed else "\nPHASE 8: FAIL (no Risk+Controller overlap found in this corpus)")
    sys.exit(0 if passed else 1)
