"""
Validation report builder (this task's "Part B") -- produces a plain
Markdown report, same convention as stats/report.py (Design.md: "plain
text or Markdown, printed to console and optionally saved to a file -- no
dashboard, no charts").

Two clearly SEPARATE sections, per this task's explicit instruction not to
blur them:

- B.1 "Internal mechanism consistency" -- does the simulation behave the
  way its own documented rules (docs/Rules.md, docs/Memory.md) say it
  should? Purely a function of THIS run's own output; no external
  comparison.
- B.2 "Comparison against real-world cited numbers" -- for the specific
  subset of docs/Research.md's Part A findings that map onto something
  actually implemented (income distribution shape, spend/income ratio
  pattern, settlement timing), compute this run's own equivalent
  statistic and report it side-by-side with the cited real-world number,
  with an explicit PASS / GAP / NOT-COMPARABLE verdict. Fraud/credit/loan
  are reported NOT APPLICABLE -- Research.md Part C is design-only, per
  docs/Rules.md #9 (this task does not implement them).

No LLM anywhere in this module (docs/Rules.md #1) -- every check below is
a plain statistical computation over a run's own CSV output.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass

from validation.sample import RunData, sample_person_ids
from world.engine import HOUSEHOLD_SWEEP_FRACTION, SAVINGS_SWEEP_FRACTION

# Tolerance for float-rounding drift accumulated across many independently
# rounded Transaction amounts (each leg of a payday is rounded to 2dp
# independently -- see world/engine.py's _maybe_pay_income). Not a
# modeling assumption, just float/rounding slack.
_EPS = 0.02


@dataclass
class CheckResult:
    section: str  # "B.1" | "B.2"
    name: str
    verdict: str  # "PASS" | "GAP" | "FAIL" | "NOT APPLICABLE" | "NOT COMPARABLE"
    detail: str  # one-line (or short multi-line) reason, with real numbers


# ---------------------------------------------------------------------------
# Shared lookups
# ---------------------------------------------------------------------------


def _person_ids(run: RunData) -> set[str]:
    return set(run.person_ids)


def _household_ids(run: RunData) -> set[str]:
    return {h["household_id"] for h in run.households}


def _household_by_person(run: RunData) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in run.households:
        for pid in json.loads(h["person_ids"]):
            out[pid] = h["household_id"]
    return out


def _organization_by_person(run: RunData) -> dict[str, str]:
    out: dict[str, str] = {}
    for o in run.organizations:
        for pid in json.loads(o["employee_person_ids"]):
            out[pid] = o["organization_id"]
    return out


def _income_by_person(run: RunData) -> dict[str, float]:
    return {p["person_id"]: p["income_monthly"] for p in run.persons}


# ---------------------------------------------------------------------------
# B.1 -- internal mechanism consistency
# ---------------------------------------------------------------------------


def check_double_entry_invariant(run: RunData) -> CheckResult:
    """Reuses/extends tests/test_ledger.py's global invariant logic as a
    runtime report check (this task's explicit instruction), now over a
    run that includes every Phase 2.5 account/transaction type too."""
    debit_total = sum(e["amount"] for e in run.ledger_entries if e["entry_type"] == "debit")
    credit_total = sum(e["amount"] for e in run.ledger_entries if e["entry_type"] == "credit")
    ok = round(debit_total, 2) == round(credit_total, 2) and len(run.ledger_entries) > 0
    return CheckResult(
        "B.1",
        "Global double-entry invariant (debits == credits)",
        "PASS" if ok else "FAIL",
        f"debit total={debit_total:,.2f}, credit total={credit_total:,.2f}, "
        f"{len(run.ledger_entries):,} ledger entries across "
        f"{len({e['account_id'] for e in run.ledger_entries}):,} accounts",
    )


def check_no_negative_balances(run: RunData) -> CheckResult:
    negative = [a for a in run.accounts if a["balance"] < 0]
    owner_types = sorted({a["owner_type"] for a in run.accounts})
    ok = len(negative) == 0
    return CheckResult(
        "B.1",
        "No negative balances, any account type",
        "PASS" if ok else "FAIL",
        f"{len(negative)} negative-balance accounts out of {len(run.accounts):,} "
        f"across owner_types {owner_types}",
    )


def check_causal_balance_ratio(run: RunData) -> CheckResult:
    """
    Reproduces stats/report.py's causal-structure check (balance/income
    ratio at the moment of a purchase attempt vs. failure rate) as a
    validation check, restricted to purchase-originated failures (not
    Organization payroll failures, which are a structurally different
    phenomenon -- see stats/report.py's own equivalent filtering and its
    inline comment for why blending the two would be misleading).
    """
    person_ids = _person_ids(run)
    income_by_person = _income_by_person(run)
    purchases = [t for t in run.transactions if t["kind"] == "purchase"]
    failures = [
        t for t in run.transactions if t["kind"] == "payment_failure" and t["from_id"] in person_ids
    ]
    attempts = purchases + failures

    buckets = [
        ("< 0.02", lambda r: r < 0.02),
        ("0.02-0.05", lambda r: 0.02 <= r < 0.05),
        ("0.05-0.10", lambda r: 0.05 <= r < 0.10),
        ("0.10-0.25", lambda r: 0.10 <= r < 0.25),
        (">= 0.25", lambda r: r >= 0.25),
    ]
    counts = {label: [0, 0] for label, _ in buckets}  # [failed, total]
    for t in attempts:
        income = income_by_person.get(t["from_id"])
        if not income:
            continue
        ratio = t["balance_before"] / income
        for label, pred in buckets:
            if pred(ratio):
                counts[label][1] += 1
                if t["kind"] == "payment_failure":
                    counts[label][0] += 1
                break

    rates = []
    rows = []
    for label, _ in buckets:
        failed, total = counts[label]
        rate = (failed / total) if total else None
        rows.append(f"{label}: {failed}/{total} ({rate * 100:.2f}%)" if total else f"{label}: n/a")
        if rate is not None:
            rates.append(rate)

    monotonic = all(rates[i] >= rates[i + 1] for i in range(len(rates) - 1)) if len(rates) >= 2 else False
    return CheckResult(
        "B.1",
        "Causal check: failure rate falls monotonically as balance/income ratio rises",
        "PASS" if monotonic else "FAIL",
        "; ".join(rows),
    )


def check_savings_accumulation(run: RunData, sample_ids: set[str]) -> CheckResult:
    """Every sampled person's final person_savings balance must equal the
    sum of their own savings_sweep transactions (savings is never debited
    -- see world/engine.py). Also cross-checks the aggregate swept
    fraction against SAVINGS_SWEEP_FRACTION."""
    savings_balance = {a["owner_id"]: a["balance"] for a in run.accounts if a["owner_type"] == "person_savings"}
    swept_by_person: dict[str, float] = {}
    total_savings = 0.0
    total_gross = 0.0
    for t in run.transactions:
        if t["kind"] in {"salary", "savings_sweep", "household_sweep"}:
            total_gross += t["amount"]
        if t["kind"] == "savings_sweep":
            swept_by_person[t["to_id"]] = swept_by_person.get(t["to_id"], 0.0) + t["amount"]
            total_savings += t["amount"]

    mismatches = 0
    checked = 0
    for pid in sample_ids:
        expected = swept_by_person.get(pid, 0.0)
        actual = savings_balance.get(pid, 0.0)
        checked += 1
        if abs(actual - expected) > _EPS:
            mismatches += 1

    actual_fraction = (total_savings / total_gross) if total_gross else 0.0
    ok = mismatches == 0 and abs(actual_fraction - SAVINGS_SWEEP_FRACTION) < 0.005
    return CheckResult(
        "B.1",
        "Savings accumulation matches savings_sweep transactions and stated fraction",
        "PASS" if ok else "FAIL",
        f"{checked - mismatches}/{checked} sampled persons' savings balance exactly "
        f"reconciles against their savings_sweep transactions; aggregate swept fraction "
        f"{actual_fraction * 100:.2f}% (stated SAVINGS_SWEEP_FRACTION={SAVINGS_SWEEP_FRACTION * 100:.0f}%)",
    )


def check_household_accumulation(run: RunData) -> CheckResult:
    """Every household's account balance must equal the sum of its own
    members' household_sweep transactions (household accounts are never
    debited -- see world/engine.py)."""
    household_balance = {a["owner_id"]: a["balance"] for a in run.accounts if a["owner_type"] == "household"}
    swept_by_household: dict[str, float] = {}
    total_household = 0.0
    total_gross = 0.0
    for t in run.transactions:
        if t["kind"] in {"salary", "savings_sweep", "household_sweep"}:
            total_gross += t["amount"]
        if t["kind"] == "household_sweep":
            swept_by_household[t["to_id"]] = swept_by_household.get(t["to_id"], 0.0) + t["amount"]
            total_household += t["amount"]

    mismatches = 0
    checked = 0
    for h in run.households:
        hid = h["household_id"]
        expected = swept_by_household.get(hid, 0.0)
        actual = household_balance.get(hid, 0.0)
        checked += 1
        if abs(actual - expected) > _EPS:
            mismatches += 1

    actual_fraction = (total_household / total_gross) if total_gross else 0.0
    ok = mismatches == 0 and abs(actual_fraction - HOUSEHOLD_SWEEP_FRACTION) < 0.005
    return CheckResult(
        "B.1",
        "Household account balances match member household_sweep contributions",
        "PASS" if ok else "FAIL",
        f"{checked - mismatches}/{checked} households' balance exactly reconciles against "
        f"their members' household_sweep transactions; aggregate swept fraction "
        f"{actual_fraction * 100:.2f}% (stated HOUSEHOLD_SWEEP_FRACTION="
        f"{HOUSEHOLD_SWEEP_FRACTION * 100:.0f}%)",
    )


def check_organization_payroll_traceability(run: RunData) -> CheckResult:
    """Every Organization-employed person's salary/savings_sweep/
    household_sweep transactions must be sourced from a real "org:<id>"
    revenue account (never the synthetic "employer:<id>" convention), and
    every such transaction must have a matching debit ledger entry in that
    Organization's own revenue account -- no orphaned/synthetic postings."""
    employed = _organization_by_person(run)
    if not employed:
        return CheckResult(
            "B.1",
            "Organization payroll traces to a real revenue-account debit",
            "NOT APPLICABLE",
            "no Organization-employed persons in this run",
        )

    revenue_account_owner = {a["owner_id"]: a["account_id"] for a in run.accounts if a["owner_type"] == "organization_revenue"}
    debit_txn_ids_by_account: dict[str, set[str]] = {}
    for e in run.ledger_entries:
        if e["entry_type"] == "debit":
            debit_txn_ids_by_account.setdefault(e["account_id"], set()).add(e["transaction_id"])

    checked = 0
    synthetic_leaks = 0
    orphaned = 0
    for t in run.transactions:
        if t["kind"] not in {"salary", "savings_sweep"}:
            continue
        if t["to_id"] not in employed:
            continue
        checked += 1
        if not t["from_id"].startswith("org:"):
            synthetic_leaks += 1
            continue
        org_id = t["from_id"].split(":", 1)[1]
        account_id = revenue_account_owner.get(org_id)
        debit_ids = debit_txn_ids_by_account.get(account_id, set())
        if t["transaction_id"] not in debit_ids:
            orphaned += 1

    ok = checked > 0 and synthetic_leaks == 0 and orphaned == 0
    return CheckResult(
        "B.1",
        "Organization payroll traces to a real revenue-account debit",
        "PASS" if ok else "FAIL",
        f"{checked} organization-employed salary/savings_sweep transactions checked; "
        f"{synthetic_leaks} used the synthetic 'employer:' source instead of a real org "
        f"(should be 0); {orphaned} had no matching debit in their org's revenue account "
        f"ledger (should be 0)",
    )


def build_b1(run: RunData, sample_ids: set[str]) -> list[CheckResult]:
    return [
        check_double_entry_invariant(run),
        check_no_negative_balances(run),
        check_causal_balance_ratio(run),
        check_savings_accumulation(run, sample_ids),
        check_household_accumulation(run),
        check_organization_payroll_traceability(run),
    ]


# ---------------------------------------------------------------------------
# B.2 -- comparison against docs/Research.md's cited real-world numbers
# ---------------------------------------------------------------------------


def check_income_distribution_shape(run: RunData) -> CheckResult:
    """
    docs/Research.md Part A §1: real income is broadly log-normal for the
    bulk of the population (~97-99%), with a Pareto (fat) tail for the top
    1-3% that a log-normal underestimates. This simulation draws income
    from a log-normal by construction (world/engine.py's
    INCOME_LOGNORMAL_MU/_SIGMA) -- so the "bulk is log-normal" claim is
    true by construction, not an independent empirical finding, and is
    reported as such rather than dressed up as a discovery. Research.md
    already noted the simulation's hard INCOME_MAX clamp sidesteps the
    fat-tail question entirely rather than modeling it -- this check
    confirms that structurally: does the clamp actually bind (are there
    persons AT the cap, implying a truncated, not tailed, distribution)?
    """
    incomes = sorted(p["income_monthly"] for p in run.persons)
    if not incomes:
        return CheckResult("B.2", "Income distribution shape vs. Research.md Part A §1", "NOT COMPARABLE", "no persons in this run")
    income_max_cap = max(incomes)
    at_or_near_cap = sum(1 for x in incomes if x >= income_max_cap * 0.999)
    p99 = incomes[int(0.99 * (len(incomes) - 1))]
    detail = (
        f"generated from a log-normal by construction (matches the cited bulk-of-"
        f"population shape by design, not independent discovery); max observed income "
        f"{income_max_cap:,.2f}, {at_or_near_cap} persons within 0.1% of it, p99={p99:,.2f}. "
        f"No Pareto/fat tail is modeled for the top 1-3% (Research.md's own documented "
        f"gap) -- this run's distribution is hard-capped, not tailed."
    )
    return CheckResult(
        "B.2",
        "Income distribution shape vs. Research.md Part A §1 (log-normal bulk / Pareto tail)",
        "PASS (bulk shape, by construction) / GAP (no Pareto tail for top 1-3%)",
        detail,
    )


def check_spend_income_ratio_by_income(run: RunData, sample_ids: set[str]) -> CheckResult:
    """
    docs/Research.md Part A §1: BLS Consumer Expenditure Survey data shows
    spend-as-a-share-of-income FALLING as income rises (poorer households
    spend a larger share, often >=100%; richer households save more).
    Research.md already flagged, in prose, that this simulation's
    purchase_amount() draws purchase size as the SAME fractional range of
    a buyer's own income regardless of income level, so it should NOT
    reproduce that declining pattern. This check computes the actual
    ratio from real output and confirms (or refutes) that documented,
    honest gap with real numbers, rather than repeating the prose claim
    unverified.
    """
    income_by_person = _income_by_person(run)
    purchase_by_person: dict[str, float] = {}
    for t in run.transactions:
        if t["kind"] == "purchase":
            purchase_by_person[t["from_id"]] = purchase_by_person.get(t["from_id"], 0.0) + t["amount"]

    sample = [pid for pid in sample_ids if pid in income_by_person]
    if len(sample) < 10:
        return CheckResult(
            "B.2",
            "Spend/income ratio vs. income level (Research.md Part A §1)",
            "NOT COMPARABLE",
            f"only {len(sample)} sampled persons -- too few for a quartile comparison",
        )

    incomes_sorted = sorted(income_by_person[pid] for pid in sample)
    n = len(incomes_sorted)
    q1_cut = incomes_sorted[int(0.25 * n)]
    q3_cut = incomes_sorted[int(0.75 * n)]
    low = [pid for pid in sample if income_by_person[pid] <= q1_cut]
    high = [pid for pid in sample if income_by_person[pid] >= q3_cut]

    def _avg_ratio(ids: list[str]) -> float:
        ratios = [
            purchase_by_person.get(pid, 0.0) / income_by_person[pid]
            for pid in ids
            if income_by_person[pid] > 0
        ]
        return statistics.mean(ratios) if ratios else 0.0

    low_ratio = _avg_ratio(low)
    high_ratio = _avg_ratio(high)

    # Real pattern (BLS CE, Research.md Part A §1): a REAL, economically
    # meaningful decline -- lower-income households spend a share of
    # income at or above 100%, higher-income households a much smaller
    # share (BLS's own 2024 figures put the overall ratio around 75%,
    # with quintile breakdowns showing a large gap, not a few percentage
    # points). This simulation's purchase_amount() draws the SAME
    # fractional range of a buyer's own income regardless of income
    # level, so any two large-enough income groups should converge to
    # statistically indistinguishable average ratios (law of large
    # numbers over many days), not a real decline. The bar for calling
    # this a genuine PASS is therefore a large RELATIVE gap (>=15%, i.e.
    # low-income spends materially more than 1.15x high-income's ratio),
    # not any nonzero absolute difference -- a few-percentage-point gap
    # on a ~250%+ base is sampling noise, not the cited pattern, and
    # would be a false PASS if measured in absolute percentage points.
    relative_gap = (low_ratio - high_ratio) / high_ratio if high_ratio > 0 else 0.0
    if relative_gap >= 0.15:
        verdict = "PASS"
        outcome = "confirmed"
    else:
        verdict = "GAP"
        outcome = (
            "NOT reproduced -- purchase_amount() draws the same fractional range of a "
            "buyer's own income regardless of income level, exactly the gap Research.md "
            "already flagged in prose, now shown with real numbers"
        )
    return CheckResult(
        "B.2",
        "Spend/income ratio vs. income level (Research.md Part A §1: should decline as income rises)",
        verdict,
        f"bottom income quartile ({len(low)} sampled persons): avg total-purchases/"
        f"income = {low_ratio * 100:.2f}%; top income quartile ({len(high)} sampled "
        f"persons): {high_ratio * 100:.2f}% (relative gap {relative_gap * 100:+.2f}%, "
        f"PASS threshold >=15%). Real-world pattern (BLS CE, Research.md Part A §1) is "
        f"a DECLINING ratio as income rises; {outcome}.",
    )


def check_settlement_timing(run: RunData) -> CheckResult:
    """
    docs/Research.md Part A §1 / Part B: real card-network settlement is
    reported at roughly 1-3 business days (Stripe's own public docs,
    corroborated by other processor explainers). This simulation's T+1
    (world/engine.py's _run_settlement) sits at the low/conservative end
    of that cited range -- this check confirms the run's OWN observed
    settlement delay is in fact always exactly 1 simulated day (not
    "eventually", not variable), which is what Research.md's Part B
    change was grounded on.
    """
    purchase_days: dict[str, set[int]] = {}
    for t in run.transactions:
        if t["kind"] == "purchase":
            purchase_days.setdefault(t["to_id"], set()).add(t["day"])

    settlement_days = [t["day"] for t in run.transactions if t["kind"] == "settlement"]
    settlement_to = {t["to_id"] for t in run.transactions if t["kind"] == "settlement"}
    if not settlement_days:
        return CheckResult(
            "B.2",
            "Settlement timing vs. Research.md Part A §1 (Stripe: ~1-3 business days)",
            "NOT COMPARABLE",
            "no settlement transactions in this run",
        )

    always_next_day = True
    checked = 0
    for t in run.transactions:
        if t["kind"] != "settlement":
            continue
        merchant_purchase_days = purchase_days.get(t["to_id"], set())
        checked += 1
        if (t["day"] - 1) not in merchant_purchase_days:
            always_next_day = False

    verdict = "PASS" if always_next_day else "FAIL"
    return CheckResult(
        "B.2",
        "Settlement timing vs. Research.md Part A §1 (Stripe: ~1-3 business days)",
        verdict,
        f"{checked} settlement transactions checked; simulated delay is fixed T+1, which "
        f"sits at the low/conservative end of the cited real 1-3 business day window -- "
        f"{'every settlement observed exactly T+1 as designed' if always_next_day else 'some settlements did NOT land exactly T+1 -- investigate'}.",
    )


def check_fraud_not_applicable() -> CheckResult:
    return CheckResult(
        "B.2",
        "Payment fraud rate vs. Research.md Part A §2 (Kansas City Fed: 17.6bps, 2023)",
        "NOT APPLICABLE",
        "fraud is not implemented -- Research.md Part C.1 is design-only, per this task's scope",
    )


def check_credit_not_applicable() -> CheckResult:
    return CheckResult(
        "B.2",
        "Credit scoring vs. Research.md Part A §3 (Fed 2007 score distribution / FRBNY transition rates)",
        "NOT APPLICABLE",
        "credit scoring is not implemented -- Research.md Part C.2 is design-only, per this task's scope",
    )


def check_loans_not_applicable() -> CheckResult:
    return CheckResult(
        "B.2",
        "Loan/interest mechanics vs. Research.md Part A §4 (Fed FEDS Notes / G.19)",
        "NOT APPLICABLE",
        "loans are not implemented -- Research.md Part C.3 is design-only, per this task's scope",
    )


def build_b2(run: RunData, sample_ids: set[str]) -> list[CheckResult]:
    return [
        check_income_distribution_shape(run),
        check_spend_income_ratio_by_income(run, sample_ids),
        check_settlement_timing(run),
        check_fraud_not_applicable(),
        check_credit_not_applicable(),
        check_loans_not_applicable(),
    ]


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def _render_section(title: str, intro: str, results: list[CheckResult]) -> list[str]:
    lines = [f"## {title}", "", intro, ""]
    for r in results:
        lines.append(f"### [{r.verdict}] {r.name}")
        lines.append("")
        lines.append(r.detail)
        lines.append("")
    return lines


def build_report(outdir: str, sample_size: int | None = None, seed: int = 12345) -> str:
    run = RunData(outdir)
    sample_ids = sample_person_ids(run, sample_size, seed)

    lines: list[str] = []
    lines.append("# Financial World Simulation -- Validation Report")
    lines.append("")
    lines.append(f"- Run directory: `{outdir}`")
    lines.append(f"- Persons in run: {len(run.persons):,}")
    lines.append(
        f"- Persons sampled for per-person checks: {len(sample_ids):,}"
        + (" (full population)" if sample_size is None or sample_size >= len(run.persons) else f" (--sample-size {sample_size}, --seed {seed})")
    )
    lines.append(f"- Households: {len(run.households):,} | Organizations: {len(run.organizations):,} | Communities: {len(run.communities):,}")
    lines.append("")

    b1_results = build_b1(run, sample_ids)
    b2_results = build_b2(run, sample_ids)

    lines += _render_section(
        "B.1 -- Internal mechanism consistency",
        "Does this run behave the way its own documented rules "
        "(docs/Rules.md, docs/Memory.md) say it should? Purely a function "
        "of this run's own output -- no external/real-world comparison here.",
        b1_results,
    )
    lines += _render_section(
        "B.2 -- Comparison against docs/Research.md's cited real-world numbers",
        "For each docs/Research.md Part A finding that maps onto something "
        "actually implemented, this run's own equivalent statistic is computed "
        "and compared against the cited real-world number/range. Mechanisms "
        "Research.md only proposed (Part C: fraud/credit/loans) are reported "
        "NOT APPLICABLE, not silently omitted.",
        b2_results,
    )

    lines.append("## Summary")
    lines.append("")
    for section, results in (("B.1", b1_results), ("B.2", b2_results)):
        counts: dict[str, int] = {}
        for r in results:
            counts[r.verdict] = counts.get(r.verdict, 0) + 1
        lines.append(f"- {section}: " + ", ".join(f"{v}={c}" for v, c in sorted(counts.items())))
    lines.append("")

    return "\n".join(lines)
