"""
Phase 9 done check: prove the five required cases explicitly (constructed
AgentVerdicts, not hoped-for examples from real data), then apply the engine
to every verdict in every real Phase 8 compound case across the full corpus
(zero LLM cost) for a full-scale sanity check.

Run directly: `python -m financial_system.policy.runner`
"""
from __future__ import annotations

import sys
from collections import Counter

from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.store import FinancialStateStore
from financial_system.orchestrator.orchestrator import process_payment
from financial_system.policy.engine import evaluate
from financial_system.verdict import AgentVerdict


def _case(label: str, verdict: AgentVerdict, has_conflict: bool, expected_outcome: str) -> bool:
    decision = evaluate(verdict, has_conflict)
    ok = decision.outcome == expected_outcome
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    print(f"    verdict: agent={verdict.agent} decision={verdict.decision} "
          f"decision_score={verdict.decision_score} "
          f"investigation_confidence={verdict.investigation_confidence} "
          f"proposed_action={verdict.proposed_action}")
    print(f"    policy:  outcome={decision.outcome} rule={decision.rule_id}")
    if not ok:
        print(f"    EXPECTED {expected_outcome}, GOT {decision.outcome}")
    return ok


def run_required_cases() -> bool:
    print("-- Phase 9 required cases --\n")
    results = []

    v1 = AgentVerdict(agent="risk", subject="dev_low_risk", decision="RELEASE", reason="no signal",
                       evidence=[], decision_score=0.05, proposed_action="NONE", affected_entities=[])
    results.append(_case("1. High-confidence low-risk action allowed", v1, False, "ALLOW"))

    v2 = AgentVerdict(agent="risk", subject="dev_high_risk", decision="HOLD", reason="burst detected",
                       evidence=[], decision_score=0.85, proposed_action="HOLD_PAYMENT", affected_entities=[])
    results.append(_case("2. Risk HOLD blocks action", v2, False, "BLOCK"))

    # Domain conflict: an action that would normally ALLOW (a healthy-looking
    # RETRY) still gets escalated once a conflict is flagged for this subject
    # -- proves the conflict check overrides a normally-approving rule.
    v3 = AgentVerdict(agent="recovery", subject="pay_conflict", decision="RETRY",
                       reason="technical_failure", evidence=[], decision_score=0.85,
                       proposed_action="RETRY_PAYMENT", affected_entities=[])
    results.append(_case("3. Domain conflict escalates even a normally-allowed action", v3, True, "ESCALATE"))

    base_kwargs = dict(agent="controller", subject="sett_ambiguous", decision="INVESTIGATE",
                        reason="unexplained gap", evidence=[], decision_score=0.0,
                        proposed_action="ESCALATE_WITH_INVESTIGATION", affected_entities=[])
    d_low = evaluate(AgentVerdict(**base_kwargs, investigation_confidence=0.1), False)
    d_none = evaluate(AgentVerdict(**base_kwargs, investigation_confidence=None), False)
    ok4 = d_low.outcome == d_none.outcome == "ESCALATE"
    print(f"[{'PASS' if ok4 else 'FAIL'}] 4. investigation_confidence never changes the outcome "
          f"(confidence=0.1 -> {d_low.outcome}, confidence=None -> {d_none.outcome})")
    results.append(ok4)

    v5 = AgentVerdict(agent="recovery", subject="pay_boundary", decision="RETRY",
                       reason="issuer_declined, base_success_rate=0.20", evidence=[],
                       decision_score=0.20, investigation_confidence=0.99,  # deliberately high -- must be ignored
                       proposed_action="RETRY_ALT_METHOD", affected_entities=[])
    d5 = evaluate(v5, False)
    ok5 = d5.outcome != "ALLOW"
    print(f"[{'PASS' if ok5 else 'FAIL'}] 5. Boundary: investigation_confidence=0.99 does NOT authorize "
          f"a decision_score=0.20 action (outcome={d5.outcome}, rule={d5.rule_id})")
    results.append(ok5)

    return all(results)


def run_full_corpus_check(graph, payment_ids: list[str]) -> None:
    outcome_counts = Counter()
    rule_counts = Counter()
    for i, pid in enumerate(payment_ids, 1):
        case = process_payment(graph, pid, investigate=False)
        has_conflict = bool(case.conflicts)
        for verdict in (case.controller_verdict, case.risk_verdict, case.recovery_verdict):
            if verdict is None:
                continue
            decision = evaluate(verdict, has_conflict)
            outcome_counts[decision.outcome] += 1
            rule_counts[decision.rule_id] += 1
        if i % 250 == 0 or i == len(payment_ids):
            print(f"  [{i}/{len(payment_ids)}]")

    print(f"\n-- Policy outcomes across {len(payment_ids)} payments' verdicts --")
    print(f"Outcomes: {dict(outcome_counts)}")
    print(f"Rules fired: {dict(rule_counts)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    passed = run_required_cases()
    print()

    print("Building graph...")
    state, graph = build_graph()
    payment_ids = [r["payment_id"] for r in state.all_rows("payments")]
    print(f"Applying Policy to {len(payment_ids)} payments' compound cases...")
    run_full_corpus_check(graph, payment_ids)

    print("\nPHASE 9: PASS" if passed else "\nPHASE 9: FAIL")
    sys.exit(0 if passed else 1)
