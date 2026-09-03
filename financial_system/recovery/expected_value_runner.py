"""
Held-out comparison: does expected-value decisioning actually change
anything, and for principled reasons -- or does it just reproduce the
existing category-level RETRY decision on every real payment in this
corpus? Run across every real failed payment (zero LLM cost,
investigate=False), not a hand-picked example. If ev_runner finds zero
divergence, or divergence for reasons that don't hold up, that is a real
result and gets reported as such -- this file's job is to find out, not to
confirm a predetermined conclusion.

Run directly: `python -m financial_system.recovery.expected_value_runner`
"""
from __future__ import annotations

import sys
from pathlib import Path

from financial_system.financial_graph.builder import build_graph
from financial_system.recovery.expected_value import compute_expected_value
from financial_system.recovery.signals import compute_recovery_signals

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def run(graph, payment_ids: list[str]) -> list:
    results = []
    for pid in payment_ids:
        signals = compute_recovery_signals(graph, pid)
        ev = compute_expected_value(graph, pid, signals)
        if ev is not None:
            results.append(ev)
    return results


def print_report(results: list) -> None:
    total = len(results)
    diverging = [r for r in results if r.diverges]

    print(f"\n-- Recovery Expected-Value comparison ({total} category-RETRY-eligible payments) --")
    print(f"Diverging cases (category says RETRY, EV says DO_NOT_RETRY): {len(diverging)}/{total}")

    from collections import Counter
    tier_counts = Counter(r.risk_tier for r in results)
    print(f"Risk-tier distribution across these payments: {dict(tier_counts)}")

    tier_divergence = Counter(r.risk_tier for r in diverging)
    print(f"Divergence by risk tier: {dict(tier_divergence)}")

    if diverging:
        print(f"\n{'payment_id':<16}{'value':>10}{'base_p':>8}{'tier':>7}{'harm_cost':>11}{'fee_cost':>9}{'EV':>10}")
        for r in diverging[:15]:
            print(f"{r.payment_id:<16}{r.value:>10.2f}{r.base_success_rate:>8.2f}{r.risk_tier:>7}"
                  f"{r.harm_cost:>11.2f}{r.fee_cost:>9.2f}{r.expected_value:>10.2f}")
        if len(diverging) > 15:
            print(f"... and {len(diverging) - 15} more")

        example = diverging[0]
        print(f"\nWorked example -- {example.payment_id}:")
        print(f"  value=Rs.{example.value:.2f}, category base_success_rate={example.base_success_rate:.0%}")
        print(f"  fee_cost=Rs.{example.fee_cost:.2f} (2% of value)")
        print(f"  risk_tier={example.risk_tier}, harm_rate={example.harm_rate:.3f}, "
              f"harm_cost=Rs.{example.harm_cost:.2f}")
        print(f"  EV = {example.base_success_rate:.2f}*{example.value:.2f} - {example.fee_cost:.2f} "
              f"- {example.harm_cost:.2f} = Rs.{example.expected_value:.2f}")
        print(f"  Category-level Recovery says: RETRY")
        print(f"  Expected-value says:          DO_NOT_RETRY")
    else:
        print("\nNo divergence found in this corpus. Reporting as-is: on this dataset, expected-value "
              "decisioning does not change any category-level recovery decision.")

    # Also report the non-diverging population's EV sign distribution, so a
    # positive-but-not-diverging case can be sanity-checked too.
    non_diverging_negative = [r for r in results if not r.diverges and r.expected_value <= 0]
    if non_diverging_negative:
        print(f"\n(sanity check: {len(non_diverging_negative)} cases have EV<=0 but were already excluded "
              f"above -- should be impossible under this module's own logic, investigate if non-zero)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Building graph...")
    state, graph = build_graph()
    payment_ids = [r["payment_id"] for r in state.all_rows("payments")]
    print(f"Scanning {len(payment_ids)} payments...")
    results = run(graph, payment_ids)
    print_report(results)
