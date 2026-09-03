"""
Phase 10 done check: prove the five required cases (two constructed directly
for full control, three using real payments so the closed loop is
demonstrated on genuine data, not a synthetic stand-in), then run the full
loop across all 160 failed payments (zero LLM cost, investigate=False).

Run directly: `python -m financial_system.action.runner`
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

from financial_system.action.loop import run_action_loop
from financial_system.action.simulator import execute_action
from financial_system.financial_graph.builder import build_graph
from financial_system.policy.engine import evaluate
from financial_system.verdict import AgentVerdict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "recovery_labels.csv"


def load_labels() -> list[dict]:
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_required_cases(graph) -> bool:
    print("-- Phase 10 required cases --\n")
    results = []

    # 1. Unauthorized action cannot execute
    v1 = AgentVerdict(agent="risk", subject="dev_x", decision="HOLD", reason="burst detected",
                       evidence=[], decision_score=0.9, proposed_action="HOLD_PAYMENT", affected_entities=[])
    d1 = evaluate(v1, False)
    executed1, action1, _ = execute_action(v1, d1)
    ok1 = d1.outcome == "BLOCK" and not executed1
    print(f"[{'PASS' if ok1 else 'FAIL'}] 1. Unauthorized action cannot execute "
          f"(policy={d1.outcome}, executed={executed1})")
    results.append(ok1)

    # 2. Authorized action executes
    v2 = AgentVerdict(agent="risk", subject="dev_y", decision="RELEASE", reason="clean",
                       evidence=[], decision_score=0.05, proposed_action="NONE", affected_entities=[])
    d2 = evaluate(v2, False)
    executed2, action2, _ = execute_action(v2, d2)
    ok2 = d2.outcome == "ALLOW" and executed2
    print(f"[{'PASS' if ok2 else 'FAIL'}] 2. Authorized action executes "
          f"(policy={d2.outcome}, executed={executed2}, action={action2})")
    results.append(ok2)

    labels = load_labels()
    # Recovery always proposes RETRY for any recoverable category (signals.py);
    # it's Policy's R3/R4 threshold (0.5) that decides ALLOW vs REVIEW. Restrict
    # to categories that actually clear it (technical_failure=.85, timeout=.80,
    # authentication_failure=.55) so these two tests genuinely exercise
    # execution, not a REVIEW-and-stop case that never reaches the gateway.
    executable_categories = {"technical_failure", "timeout", "authentication_failure"}

    # 3. Successful action closes the case -- a real payment whose category is
    # recoverable AND whose (simulated) gateway outcome actually succeeds.
    succeed_case = next(r for r in labels if r["failure_reason"] in executable_categories
                         and r["retry_would_succeed"] == "True")
    case3 = run_action_loop(graph, succeed_case["payment_id"], investigate=False)
    ok3 = case3.case_status == "RESOLVED" and len(case3.attempts) == 1
    print(f"[{'PASS' if ok3 else 'FAIL'}] 3. Successful retry closes the case "
          f"({succeed_case['payment_id']}, status={case3.case_status}, attempts={len(case3.attempts)})")
    results.append(ok3)

    # 4. Failed action re-enters investigation -> new decision -> policy -> action:
    # a real payment whose category IS recoverable (and executable) but whose
    # specific retry fails.
    fail_case = next(r for r in labels if r["failure_reason"] in executable_categories
                      and r["retry_would_succeed"] == "False")
    case4 = run_action_loop(graph, fail_case["payment_id"], investigate=False)
    ok4 = (len(case4.attempts) == 2
           and case4.attempts[0].verification_result == "FAILURE"
           and case4.attempts[0].action_taken.startswith("RETRY")
           and case4.attempts[1].verdict.decision == "ESCALATE"
           and case4.case_status in ("ESCALATE", "ESCALATED"))
    print(f"[{'PASS' if ok4 else 'FAIL'}] 4. Failed retry re-enters the loop and escalates "
          f"({fail_case['payment_id']}, attempts={len(case4.attempts)}, "
          f"attempt1_result={case4.attempts[0].verification_result}, "
          f"attempt2_decision={case4.attempts[1].verdict.decision if len(case4.attempts) > 1 else None}, "
          f"final_status={case4.case_status})")
    results.append(ok4)

    # 5. Verification cannot rewrite history -- the original (failed) attempt
    # is still intact after the follow-up attempt was appended.
    original = case4.attempts[0]
    ok5 = (original.attempt_number == 1 and original.action_taken.startswith("RETRY")
           and original.verification_result == "FAILURE"
           and original.verdict.decision == "RETRY")
    print(f"[{'PASS' if ok5 else 'FAIL'}] 5. Verification does not rewrite history "
          f"(attempt 1 still shows: action={original.action_taken}, "
          f"verification={original.verification_result}, original_decision={original.verdict.decision})")
    results.append(ok5)

    return all(results)


def run_full_batch(graph, labels: list[dict]) -> None:
    status_counts = Counter()
    attempt_counts = Counter()
    for i, row in enumerate(labels, 1):
        case = run_action_loop(graph, row["payment_id"], investigate=False)
        status_counts[case.case_status] += 1
        attempt_counts[len(case.attempts)] += 1
        if i % 40 == 0 or i == len(labels):
            print(f"  [{i}/{len(labels)}]")

    print(f"\n-- Full batch over {len(labels)} failed payments --")
    print(f"Case status: {dict(status_counts)}")
    print(f"Attempts per case: {dict(attempt_counts)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Building graph...")
    state, graph = build_graph()

    passed = run_required_cases(graph)
    print()

    labels = load_labels()
    print(f"Running Action+Verification loop over all {len(labels)} failed payments...")
    run_full_batch(graph, labels)

    print("\nPHASE 10: PASS" if passed else "\nPHASE 10: FAIL")
    sys.exit(0 if passed else 1)
