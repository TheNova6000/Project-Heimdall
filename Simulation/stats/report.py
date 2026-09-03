"""
Post-run descriptive statistics (Architecture.md, Design.md).

Design.md: "plain text or Markdown, printed to console and optionally
saved to a file -- no dashboard, no charts... A table of numbers is
enough for Phase 1's purpose: proving the mechanism works, not
presenting it."

This report exists to answer PRD.md's actual research question -- does
this simulation's output have real causal structure a payment's outcome
depends on the paying agent's own state, unlike financial_system's
per-category coin flip? -- not merely to look like a polished dashboard.
The "mechanism check" section is the load-bearing part of this file;
everything else is standard descriptive-stats bookkeeping.

Usage:
    python stats/report.py --outdir output
    python stats/report.py --outdir output --save output/report.md
"""

from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys


def _read_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _fmt(x: float, nd: int = 2) -> str:
    return f"{x:,.{nd}f}"


def build_report(outdir: str) -> str:
    txns = _read_csv(os.path.join(outdir, "transactions.csv"))
    persons = _read_csv(os.path.join(outdir, "persons.csv"))
    events = _read_csv(os.path.join(outdir, "events.csv"))

    for row in txns:
        row["amount"] = float(row["amount"])
        row["balance_before"] = float(row["balance_before"])
        row["day"] = int(row["day"])

    lines: list[str] = []
    lines.append("# Financial World Simulation -- Phase 1 Descriptive Statistics")
    lines.append("")

    # -- Volume ------------------------------------------------------------
    by_kind: dict[str, list[dict]] = {}
    for row in txns:
        by_kind.setdefault(row["kind"], []).append(row)

    num_days = (max(r["day"] for r in txns) + 1) if txns else 0
    lines.append("## Volume")
    lines.append("")
    lines.append(f"- Persons: {len(persons)}")
    lines.append(f"- Simulated days: {num_days}")
    lines.append(f"- Transactions (total rows): {len(txns)}")
    lines.append(f"- Events: {len(events)}")
    for kind in sorted(by_kind):
        rows = by_kind[kind]
        lines.append(f"  - {kind}: {len(rows)} ({100 * len(rows) / len(txns):.1f}%)")
    if num_days:
        lines.append(f"- Avg transactions/day: {_fmt(len(txns) / num_days)}")
    lines.append("")

    # -- Failure rate --------------------------------------------------------
    purchases = by_kind.get("purchase", [])
    failures = by_kind.get("payment_failure", [])
    attempts = purchases + failures
    lines.append("## Payment failure rate")
    lines.append("")
    if attempts:
        rate = 100 * len(failures) / len(attempts)
        lines.append(f"- Purchase attempts (purchase + payment_failure): {len(attempts)}")
        lines.append(f"- Failed: {len(failures)} ({rate:.2f}%)")
        lines.append(f"- Succeeded: {len(purchases)} ({100 - rate:.2f}%)")
    else:
        lines.append("- No purchase attempts recorded.")
    lines.append("")

    # -- Amount distribution (successful purchases) ---------------------------
    lines.append("## Purchase amount distribution (successful purchases)")
    lines.append("")
    amounts = [r["amount"] for r in purchases]
    if amounts:
        amounts_sorted = sorted(amounts)
        n = len(amounts_sorted)
        lines.append(f"- count: {n}")
        lines.append(f"- min: {_fmt(amounts_sorted[0])}")
        lines.append(f"- p25: {_fmt(amounts_sorted[int(0.25 * n)])}")
        lines.append(f"- median: {_fmt(statistics.median(amounts_sorted))}")
        lines.append(f"- p75: {_fmt(amounts_sorted[int(0.75 * n)])}")
        lines.append(f"- p95: {_fmt(amounts_sorted[min(n - 1, int(0.95 * n))])}")
        lines.append(f"- max: {_fmt(amounts_sorted[-1])}")
        lines.append(f"- mean: {_fmt(statistics.mean(amounts))}")
        if n > 1:
            lines.append(f"- stdev: {_fmt(statistics.stdev(amounts))}")
    else:
        lines.append("- No successful purchases recorded.")
    lines.append("")

    # -- End-of-run balance distribution --------------------------------------
    lines.append("## End-of-run Person balance distribution")
    lines.append("")
    balances = [float(p["balance"]) for p in persons]
    if balances:
        bs = sorted(balances)
        n = len(bs)
        lines.append(f"- min: {_fmt(bs[0])}")
        lines.append(f"- median: {_fmt(statistics.median(bs))}")
        lines.append(f"- max: {_fmt(bs[-1])}")
        lines.append(f"- mean: {_fmt(statistics.mean(bs))}")
        negative = sum(1 for b in bs if b < 0)
        lines.append(f"- balances < 0: {negative} (must be 0 -- Rules.md #7)")
    lines.append("")

    # -- Mechanism check: is failure actually caused by balance state? -------
    lines.append("## Causal-structure check (this project's central question)")
    lines.append("")
    lines.append(
        "PRD.md's hypothesis: a payment should fail *because* the paying "
        "agent's own balance was insufficient at that moment, not because "
        "an independent per-category probability was drawn (the limitation "
        "found in financial_system's generator)."
    )
    lines.append("")
    violations = sum(1 for r in failures if not (r["balance_before"] < r["amount"]))
    lines.append(
        f"- payment_failure rows where balance_before < amount: "
        f"{len(failures) - violations}/{len(failures)} "
        f"({'OK -- mechanism holds by construction' if violations == 0 else 'VIOLATIONS FOUND -- bug'})"
    )
    lines.append(
        "  (This is close to tautological by construction -- Bank.debit only "
        "ever returns False when balance_before < amount, see world/agents/bank.py "
        "-- but it is the direct, inspectable, per-transaction evidence that the "
        "failure traces to that specific agent's state at that specific moment, "
        "not to a label. The more interesting question is below.)"
    )
    lines.append("")

    # Per-person failure rate vs. their own income (proxy for "who tends to
    # be cash-strapped"): if the hypothesis has real bite, low-income
    # persons -- who saturate their spend_probability's balance_factor less
    # often (see world/agents/person.py) -- should show a materially higher
    # personal failure rate than high-income persons, since heterogeneous
    # per-agent state (not a flat category rate) is what should be driving
    # outcomes here.
    income_by_person = {p["person_id"]: float(p["income_monthly"]) for p in persons}
    attempts_by_person: dict[str, list[dict]] = {}
    for r in attempts:
        attempts_by_person.setdefault(r["from_id"], []).append(r)

    incomes_sorted = sorted(income_by_person.values())
    if incomes_sorted:
        median_income = statistics.median(incomes_sorted)
        low_income_ids = {pid for pid, inc in income_by_person.items() if inc < median_income}
        high_income_ids = {pid for pid, inc in income_by_person.items() if inc >= median_income}

        def _failure_rate(ids: set) -> tuple[int, int]:
            att = sum(len(attempts_by_person.get(pid, [])) for pid in ids)
            fail = sum(
                sum(1 for r in attempts_by_person.get(pid, []) if r["kind"] == "payment_failure")
                for pid in ids
            )
            return fail, att

        lf, la = _failure_rate(low_income_ids)
        hf, ha = _failure_rate(high_income_ids)
        lines.append("### Failure rate by income group (below- vs at/above-median income)")
        lines.append("")
        lines.append(f"- Below-median income ({len(low_income_ids)} persons): "
                      f"{lf}/{la} attempts failed ({(100 * lf / la) if la else 0:.2f}%)")
        lines.append(f"- At/above-median income ({len(high_income_ids)} persons): "
                      f"{hf}/{ha} attempts failed ({(100 * hf / ha) if ha else 0:.2f}%)")
        lines.append("")
        if la and ha and hf / ha > 0:
            ratio = (lf / la) / (hf / ha)
            lines.append(
                f"- Below-median-income failure rate is {ratio:.2f}x the "
                f"at/above-median rate."
            )
        lines.append(
            "  If this ratio is meaningfully > 1, failures are concentrating "
            "among lower-income (structurally lower-balance-factor) persons, "
            "which is the kind of heterogeneous, state-dependent pattern the "
            "current financial_system generator's flat per-category rate "
            "cannot produce. If it is close to 1, that is also a valid, "
            "honestly-reported Phase 1 finding (Rules.md #5, #9)."
        )
    lines.append("")

    # -- Failure rate by balance-to-income ratio at the moment of attempt ----
    # A sharper cut than the income-group split above: bucket every purchase
    # attempt by balance_before / income_monthly *at the moment of that
    # attempt* (not the person's income level itself, which the section
    # above showed is confounded -- purchase size also scales with income,
    # so raw income group is a weak predictor). This isolates the one
    # variable the hypothesis actually claims matters: how much of a
    # cash cushion the agent had right then.
    lines.append("### Failure rate by balance-to-income ratio at moment of attempt")
    lines.append("")
    ratio_buckets = [
        ("< 0.02", lambda r: r < 0.02),
        ("0.02 - 0.05", lambda r: 0.02 <= r < 0.05),
        ("0.05 - 0.10", lambda r: 0.05 <= r < 0.10),
        ("0.10 - 0.25", lambda r: 0.10 <= r < 0.25),
        (">= 0.25", lambda r: r >= 0.25),
    ]
    bucket_counts = {label: [0, 0] for label, _ in ratio_buckets}  # [failed, total]
    for r in attempts:
        income = income_by_person.get(r["from_id"])
        if not income:
            continue
        ratio = r["balance_before"] / income
        for label, pred in ratio_buckets:
            if pred(ratio):
                bucket_counts[label][1] += 1
                if r["kind"] == "payment_failure":
                    bucket_counts[label][0] += 1
                break
    lines.append("| balance_before / income_monthly | attempts | failed | failure rate |")
    lines.append("|---|---|---|---|")
    for label, _ in ratio_buckets:
        failed, total = bucket_counts[label]
        rate = f"{100 * failed / total:.2f}%" if total else "n/a"
        lines.append(f"| {label} | {total} | {failed} | {rate} |")
    lines.append("")
    lines.append(
        "A monotonically decreasing failure rate down these rows is the "
        "clearest evidence that failure is being driven by each agent's own "
        "balance state at the moment of the attempt, not by a fixed "
        "per-category rate -- this is the structure financial_system's "
        "generator lacks (PRD.md 'Why')."
    )
    lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute Phase 1 descriptive statistics")
    parser.add_argument(
        "--outdir",
        type=str,
        default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output"),
        help="Directory containing persons.csv / transactions.csv / events.csv",
    )
    parser.add_argument("--save", type=str, default=None, help="Optional path to save the report as Markdown")
    args = parser.parse_args()

    report = build_report(args.outdir)
    print(report)

    if args.save:
        os.makedirs(os.path.dirname(os.path.abspath(args.save)), exist_ok=True)
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n(saved to {args.save})", file=sys.stderr)


if __name__ == "__main__":
    main()
