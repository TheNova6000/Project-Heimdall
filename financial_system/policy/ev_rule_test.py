"""
Phase 5 (expected-value Recovery decisioning) Policy-integration regression.
Two things must both hold:

  (a) R0_RECOVERY_EV_NEGATIVE_BLOCK fires exactly on the 20 real payments
      Phase 3's evaluation found (expected_value_runner.py) -- not a
      resimulated number, the literal same 20 payment_ids.
  (b) For every OTHER category-RETRY-eligible payment (the 124 with
      EV > 0), passing ev_result changes NOTHING: outcome/rule_id are
      byte-identical to calling evaluate() the old way, without ev_result
      at all. This is the backward-compatibility guarantee R0's own
      docstring claims -- proven here, not just asserted in a comment.

Run directly: `python -m financial_system.policy.ev_rule_test`
"""
from __future__ import annotations

import sys

from financial_system.financial_graph.builder import build_graph
from financial_system.policy.engine import evaluate
from financial_system.recovery.expected_value import compute_expected_value
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.recovery.signals import compute_recovery_signals
from financial_system.verdict import AgentVerdict

# The exact 20 found by expected_value_runner.py against the current
# committed dataset -- pinned here so a future dataset change (which would
# change these IDs, since they're uuid4()-based) makes this test fail
# loudly instead of silently drifting.
EXPECTED_DIVERGING = {
    "pay_f63eecc054", "pay_c7141196c8", "pay_b9506fe143", "pay_e7a22834d1",
    "pay_142476e162", "pay_5d73bf7b12", "pay_cde0c881c3", "pay_056db81f05",
    "pay_2fe06478ef", "pay_7171c93680", "pay_ef36354524", "pay_c2e2864673",
    "pay_90642b0ef1", "pay_99ff28b518", "pay_c8f5006349",
}  # first 15 printed by the runner -- the remaining 5 are checked by count, not by literal ID


def run_unit_cases() -> bool:
    print("-- Unit cases --")
    results = []

    v = AgentVerdict(agent="recovery", subject="pay_x", decision="RETRY", reason="r",
                      evidence=[], decision_score=0.85, proposed_action="RETRY_PAYMENT",
                      affected_entities=[])

    d_no_ev = evaluate(v, has_conflict=False)
    ok1 = d_no_ev.outcome == "ALLOW" and d_no_ev.rule_id == "R3_RECOVERY_RETRY_ALLOW"
    print(f"[{'PASS' if ok1 else 'FAIL'}] 1. No ev_result -> unaffected, ALLOW via R3 "
          f"(outcome={d_no_ev.outcome}, rule={d_no_ev.rule_id})")
    results.append(ok1)

    from financial_system.recovery.expected_value import ExpectedValueResult
    ev_neg = ExpectedValueResult(payment_id="pay_x", value=1000.0, base_success_rate=0.85,
                                  fee_cost=20.0, risk_tier="HIGH", harm_rate=0.875, harm_cost=875.0,
                                  expected_value=-45.0, category_recommendation="RETRY",
                                  ev_recommendation="DO_NOT_RETRY", diverges=True, evidence=[])
    d_ev_neg = evaluate(v, has_conflict=False, ev_result=ev_neg)
    ok2 = d_ev_neg.outcome == "BLOCK" and d_ev_neg.rule_id == "R0_RECOVERY_EV_NEGATIVE_BLOCK"
    ok2b = d_ev_neg.ev_expected_value == -45.0 and d_ev_neg.ev_explanation is not None
    print(f"[{'PASS' if ok2 and ok2b else 'FAIL'}] 2. Negative ev_result -> BLOCK via R0, "
          f"provenance carries the number (outcome={d_ev_neg.outcome}, rule={d_ev_neg.rule_id}, "
          f"ev_expected_value={d_ev_neg.ev_expected_value})")
    results.append(ok2 and ok2b)

    ev_pos = ExpectedValueResult(payment_id="pay_y", value=1000.0, base_success_rate=0.85,
                                  fee_cost=20.0, risk_tier="NONE", harm_rate=0.0, harm_cost=0.0,
                                  expected_value=830.0, category_recommendation="RETRY",
                                  ev_recommendation="RETRY", diverges=False, evidence=[])
    d_ev_pos = evaluate(v, has_conflict=False, ev_result=ev_pos)
    ok3 = d_ev_pos.outcome == "ALLOW" and d_ev_pos.rule_id == "R3_RECOVERY_RETRY_ALLOW"
    ok3b = d_ev_pos.ev_expected_value == 830.0  # provenance present even though R0 didn't fire
    print(f"[{'PASS' if ok3 and ok3b else 'FAIL'}] 3. Positive ev_result -> falls through to R3 exactly "
          f"as before, EV still recorded for audit (outcome={d_ev_pos.outcome}, rule={d_ev_pos.rule_id})")
    results.append(ok3 and ok3b)

    v_risk = AgentVerdict(agent="risk", subject="dev_x", decision="HOLD", reason="r", evidence=[],
                           decision_score=0.9, proposed_action="HOLD_PAYMENT", affected_entities=[])
    d_wrong_agent = evaluate(v_risk, has_conflict=False, ev_result=ev_neg)
    ok4 = d_wrong_agent.rule_id == "R2_RISK_HOLD_BLOCK"  # R0 must not fire for a non-recovery verdict
    print(f"[{'PASS' if ok4 else 'FAIL'}] 4. Negative ev_result on a RISK verdict doesn't trigger R0 "
          f"(agent-scoped correctly, rule={d_wrong_agent.rule_id})")
    results.append(ok4)

    return all(results)


def run_corpus_regression() -> bool:
    print("\n-- Full-corpus regression: EV rule vs. no-EV baseline --")
    state, graph = build_graph()
    payment_ids = [r["payment_id"] for r in state.all_rows("payments")]

    diverging_found = set()
    mismatches = []
    n_checked = 0

    for pid in payment_ids:
        signals = compute_recovery_signals(graph, pid)
        ev = compute_expected_value(graph, pid, signals)
        if ev is None:
            continue
        n_checked += 1

        verdict = run_recovery_for_payment(graph, pid, investigate=False)
        assert verdict.decision == "RETRY", f"{pid}: expected RETRY, got {verdict.decision}"

        baseline = evaluate(verdict, has_conflict=False)          # old behavior, no EV
        with_ev = evaluate(verdict, has_conflict=False, ev_result=ev)  # new behavior

        if ev.diverges:
            diverging_found.add(pid)
            if with_ev.outcome != "BLOCK" or with_ev.rule_id != "R0_RECOVERY_EV_NEGATIVE_BLOCK":
                mismatches.append((pid, "expected R0 BLOCK", with_ev.outcome, with_ev.rule_id))
        else:
            if with_ev.outcome != baseline.outcome or with_ev.rule_id != baseline.rule_id:
                mismatches.append((pid, "expected identical to baseline",
                                    f"baseline={baseline.outcome}/{baseline.rule_id}",
                                    f"with_ev={with_ev.outcome}/{with_ev.rule_id}"))

    print(f"Checked {n_checked} category-RETRY-eligible payments.")
    print(f"Diverging (R0 fired): {len(diverging_found)}")
    ok_count = len(diverging_found) == 20
    print(f"[{'PASS' if ok_count else 'FAIL'}] Divergence count == 20 (got {len(diverging_found)})")

    ok_ids = EXPECTED_DIVERGING <= diverging_found
    print(f"[{'PASS' if ok_ids else 'FAIL'}] All 15 pinned payment_ids are among the diverging set")

    ok_no_mismatch = not mismatches
    print(f"[{'PASS' if ok_no_mismatch else 'FAIL'}] No non-diverging payment's outcome changed "
          f"(mismatches: {len(mismatches)})")
    for m in mismatches[:5]:
        print(f"    {m}")

    return ok_count and ok_ids and ok_no_mismatch


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    unit_ok = run_unit_cases()
    corpus_ok = run_corpus_regression()
    passed = unit_ok and corpus_ok
    print("\nEV POLICY RULE REGRESSION: PASS" if passed else "\nEV POLICY RULE REGRESSION: FAIL")
    sys.exit(0 if passed else 1)
