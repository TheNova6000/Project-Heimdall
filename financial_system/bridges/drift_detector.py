"""
Drift detector: checks whether Heimdall's REAL, live decisions -- and their
downstream effect on a running Truman world -- are consistent with what
Truman's OWN, KNOWN, documented generative mechanisms predict. See
`docs/NORTH_STAR.md`'s "Already prefigured" section (the live-loop entry
and the Verification Engine entry) and Section 33 ("But Simulation Must
Never Become Fake Truth" -- "the system must distinguish REAL OBSERVATION /
RESEARCH-SUPPORTED MECHANISM / CALIBRATED SIMULATION... synthetic evidence
cannot silently become empirical evidence") for the conceptual grounding.
(This task's brief cited that grounding as NORTH_STAR.md's Sections 18/19
under the labels "Observability"/"Ground Truth" -- the actual section
titles at those numbers are "Preserve Deterministic Systems as the
Guarantee Layer" / "Upgrade Discovery From Answering to Investigating";
noted here plainly rather than silently substituted, per this project's own
honesty convention -- Section 33 plus the "Already prefigured" entries are
the passages that actually state this task's idea.)

WHY THIS IS POSSIBLE HERE AND NOT ON A REAL DATASET: Truman's mechanisms
are not estimated, they are KNOWN -- we built them, and every one is
labeled with its exact provenance (Simulation/docs/Rules.md #2,
Simulation/provenance/catalog.py). So instead of asking "does Heimdall's
decision look reasonable" (a fuzzy question with no verifiable answer), we
can ask a much sharper one: "does Heimdall's decision, and Truman's own
resulting causal outcome, actually agree with what Truman's own documented
mechanism predicts?" -- a precise, checkable comparison, not a vibe score.

THREE CHECKS, each pinned to one specific, cited, already-verified Truman
mechanism -- no 4th "overall health score":

  Check 1 -- Retry timing vs. Truman's payday mechanism (world/agents/
    person.py's `maybe_receive_income`: income arrives on a person's own
    fixed monthly `payday`, day-of-month 1-28, and NOWHERE else -- Truman's
    only liquidity mechanism, confirmed by reading engine.py's
    `_maybe_pay_income`/`_maybe_attempt_purchase` directly). The live loop
    (financial_system/bridges/live_recovery_loop.py) always schedules a
    RETRY exactly 1 simulated day after failure. A retry is therefore
    STRUCTURALLY DOOMED (balance cannot possibly have grown) whenever the
    target day's day-of-month != the person's own payday, and only
    GENUINELY UNCERTAIN on the day it does. This is checkable directly from
    Truman's own real ledger/persons state the live loop already produced
    -- no estimation involved.

  Check 2 -- Recovery's `decision_score` (financial_system/recovery/
    signals.py's `FAILURE_TAXONOMY["insufficient_funds"]["base_success_
    rate"]`, read live below, never hardcoded) vs. Truman's OWN realized
    retry-success rate from a real live-loop run, compared with an exact
    binomial significance test (not eyeballed).

  Check 3 (reuses the existing, non-live, batch Risk bridge -- no live Risk
    loop built) -- Truman's device-sharing mechanism (world/engine.py's
    `DEVICE_HOUSEHOLD_SHARING_FRACTION = 0.3`, Simulation/docs/Memory.md's
    "Device" section) vs. Risk's own scoring formula (financial_system/
    risk/scoring.py's `n_sharers_score = clamp((n_sharers-1)/3)`,
    `WEIGHTS["n_sharers"] = 0.15`): does the deterministic component
    Heimdall's own code says should track n_sharers actually track it on
    real bridged output, and does the overall decision_score correlate
    with n_sharers in the expected (non-negative) direction once you
    account for the fact that Truman deliberately has NO fraud-ring
    mechanism (Memory.md: "if Heimdall's Risk logic finds zero fraud rings
    ... that is the CORRECT and expected result")?

HARD SAFETY BOUNDARY: this module is READ-ONLY analysis. It calls
`run_live_recovery_loop`, `run_bridge`, and `run_simulation.run` --  all
pre-existing, unmodified functions -- and never touches financial_system/
recovery|risk|reconciliation|financial_state|financial_graph|
discovery_adapter|data, nor any existing Simulation/world/*.py file. It
writes only to caller-supplied work directories, never into financial_system/
data/raw/.
"""
from __future__ import annotations

import datetime
import math
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SIMULATION_DIR = REPO_ROOT / "Simulation"
if str(SIMULATION_DIR) not in sys.path:
    sys.path.insert(0, str(SIMULATION_DIR))

import run_simulation  # Simulation/run_simulation.py -- reused as a library, unmodified
from validation.sample import RunData  # Simulation/validation/sample.py -- reused as a library, unmodified

from financial_system.bridges.live_recovery_loop import LiveLoopReport, RetrySchedule, run_live_recovery_loop
from financial_system.bridges.run_bridge import run_bridge
from financial_system.recovery.signals import FAILURE_TAXONOMY
from financial_system.risk.scoring import WEIGHTS as RISK_WEIGHTS

ALPHA = 0.05  # significance threshold for the binomial test in Check 2, standard default


@dataclass
class CheckResult:
    check_id: str
    name: str
    verdict: str  # "MATCH" | "DRIFT-DETECTED" | "INCONCLUSIVE"
    detail: str


# ---------------------------------------------------------------------------
# Check 1 -- retry timing vs. Truman's payday mechanism
# ---------------------------------------------------------------------------


@dataclass
class RetryTimingClassification:
    sched: RetrySchedule
    target_day_of_month: int
    payday: int | None
    structurally_doomed: bool
    attempted: bool
    succeeded: bool | None


def classify_retry_timing(
    report: LiveLoopReport, run: RunData, start_date: datetime.date
) -> list[RetryTimingClassification]:
    """For every RETRY the live loop actually scheduled, classifies whether
    it was structurally doomed (target day's day-of-month != the person's
    own fixed payday -- Truman's ONLY income mechanism, so balance cannot
    possibly have grown) or genuinely uncertain (target day == payday)."""
    payday_by_person = {p["person_id"]: p["payday"] for p in run.persons}
    attempted_by_id = {r.original_transaction_id: r for r in report.retries_attempted}

    out = []
    for sched in report.retries_scheduled:
        target_date = start_date + datetime.timedelta(days=sched.target_day)
        payday = payday_by_person.get(sched.person_id)
        doomed = payday is not None and target_date.day != payday
        outcome = attempted_by_id.get(sched.original_transaction_id)
        out.append(RetryTimingClassification(
            sched=sched, target_day_of_month=target_date.day, payday=payday,
            structurally_doomed=doomed, attempted=outcome is not None,
            succeeded=(outcome.succeeded if outcome is not None else None),
        ))
    return out


def check_retry_timing_vs_payday_mechanism(
    report: LiveLoopReport, run: RunData, start_date: datetime.date
) -> CheckResult:
    name = "Retry timing vs. Truman's payday mechanism"
    classifications = classify_retry_timing(report, run, start_date)
    total = len(classifications)
    if total == 0:
        return CheckResult("1", name, "INCONCLUSIVE",
                            "0 RETRY decisions were scheduled in this run -- nothing to check.")

    doomed = [c for c in classifications if c.structurally_doomed]
    uncertain = [c for c in classifications if not c.structurally_doomed]
    doomed_attempted = [c for c in doomed if c.attempted]
    anomalies = [c for c in doomed_attempted if c.succeeded is True]  # should never happen

    frac_doomed = len(doomed) / total
    example_lines = "; ".join(
        f"{c.sched.person_id} failed day {c.sched.failure_day}, retried day {c.sched.target_day} "
        f"(day-of-month {c.target_day_of_month} != payday {c.payday})"
        for c in doomed[:3]
    ) or "n/a"

    verdict = "DRIFT-DETECTED" if anomalies else "MATCH"
    detail = (
        f"{total} RETRY decisions were scheduled for a real next-day retry attempt. Truman's ONLY income "
        f"mechanism is each person's own fixed monthly `payday` (Simulation/world/agents/person.py's "
        f"`maybe_receive_income`: income arrives iff `day_of_month == self.payday`; Simulation/docs/"
        f"Memory.md's Payday row: '1 fixed day/month per person, uniform 1-28' -- confirmed by reading "
        f"world/engine.py's `_maybe_pay_income`/`_maybe_attempt_purchase` directly: no other liquidity "
        f"mechanism exists). Because live_recovery_loop.py always schedules a retry exactly 1 simulated "
        f"day after failure (target_day = failure_day + 1 -- see its module docstring), a retry is "
        f"STRUCTURALLY DOOMED whenever the target day's day-of-month != the person's own payday (balance "
        f"cannot possibly have grown), and GENUINELY UNCERTAIN only on the ~1/28 of cases where it lands "
        f"on payday.\n"
        f"  structurally doomed:      {len(doomed)}/{total} ({frac_doomed:.1%})\n"
        f"  genuinely uncertain:      {len(uncertain)}/{total} ({1 - frac_doomed:.1%})\n"
        f"  of the {len(doomed_attempted)} structurally-doomed retries actually attempted within the run "
        f"window, {len(anomalies)} succeeded anyway (should be 0 -- a nonzero count would mean either an "
        f"undocumented liquidity mechanism in Truman, or a bug in this classification).\n"
        f"  examples (structurally doomed): {example_lines}"
    )
    return CheckResult("1", name, verdict, detail)


# ---------------------------------------------------------------------------
# Check 2 -- Recovery's decision_score vs. Truman's realized retry-success rate
# ---------------------------------------------------------------------------


def _binomial_pmf(k: int, n: int, p: float) -> float:
    return math.comb(n, k) * (p ** k) * ((1 - p) ** (n - k))


def _binomial_two_sided_pvalue(k: int, n: int, p: float) -> float:
    """Exact two-sided binomial test p-value: sum of the probabilities of
    every outcome at least as extreme (P(i) <= P(k), the standard exact
    method), not a normal approximation -- appropriate at the small n this
    project's own live-loop runs actually produce."""
    pk = _binomial_pmf(k, n, p)
    total = sum(
        pi for i in range(n + 1)
        if (pi := _binomial_pmf(i, n, p)) <= pk * (1 + 1e-9)
    )
    return min(1.0, total)


def check_decision_score_vs_realized_rate(report: LiveLoopReport) -> CheckResult:
    name = "Recovery's decision_score vs. Truman's realized retry-success rate"
    spec = FAILURE_TAXONOMY.get("insufficient_funds")
    assert spec is not None, "insufficient_funds must exist in FAILURE_TAXONOMY -- Truman's only failure category"
    decision_score = spec["base_success_rate"]

    n = len(report.retries_attempted)
    k = report.retries_succeeded

    if n == 0:
        return CheckResult("2", name, "INCONCLUSIVE",
                            f"0 retries were actually attempted in this run -- nothing to compare against "
                            f"Heimdall's decision_score={decision_score:.2f}.")
    if n < 5:
        return CheckResult("2", name, "INCONCLUSIVE",
                            f"only {n} retries were actually attempted -- too few for a reliable "
                            f"significance judgement (rule of thumb: n>=5). Observed {k}/{n} "
                            f"({k / n:.1%}) vs. Heimdall's decision_score={decision_score:.2f}; report "
                            f"honestly as inconclusive rather than forcing a verdict from this sample.")

    observed_rate = k / n
    p_value = _binomial_two_sided_pvalue(k, n, decision_score)
    significant = p_value < ALPHA
    verdict = "DRIFT-DETECTED" if significant else "MATCH"

    detail = (
        f"Heimdall's Recovery logic (financial_system/recovery/signals.py's FAILURE_TAXONOMY, read live "
        f"from the current code, not assumed) assigns decision_score={decision_score:.2f} to every "
        f"insufficient_funds RETRY -- its own stated CATEGORY-level historical retry-success rate "
        f"(recovery_agent.py's own comment: 'a base rate, never a per-instance prediction'). Truman's OWN "
        f"realized retry-success rate from this real run: {k}/{n} ({observed_rate:.1%}).\n"
        f"  Exact two-sided binomial test (H0: Truman's true retry-success probability equals Heimdall's "
        f"stated {decision_score:.2f}): p-value={p_value:.3e} at alpha={ALPHA} -> "
        f"{'statistically significant divergence' if significant else 'not statistically distinguishable from decision_score'}.\n"
        f"  Diagnosis (not, by itself, evidence Heimdall's 0.45 is wrong): decision_score is a "
        f"category-level base rate; this live loop's own retry policy always retries exactly 1 simulated "
        f"day later (RETRY_LATER's only executable schedule in this bridge -- see live_recovery_loop.py's "
        f"module docstring), against Truman's monthly-payday-only income model. Check 1 above shows this "
        f"exact mechanism directly: a near-0% realized rate under a 1-day retry window is a real, "
        f"causally-explained consequence of that assumption mismatch (short retry window vs. monthly "
        f"income cadence), not noise and not necessarily a Heimdall miscalibration in general -- see Check "
        f"1 for the causal accounting."
    )
    return CheckResult("2", name, verdict, detail)


# ---------------------------------------------------------------------------
# Check 3 (optional) -- device-sharing signal vs. Risk's decisions (batch bridge, reused)
# ---------------------------------------------------------------------------


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _pearson_r(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mean_x, mean_y = statistics.mean(xs), statistics.mean(ys)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / math.sqrt(var_x * var_y)


def check_device_sharing_vs_risk_scoring(bridge_result: dict) -> CheckResult:
    name = "Device-sharing intensity (household mechanism) vs. Risk's decision_score"
    verdicts = bridge_result.get("risk_verdicts", [])
    if not verdicts:
        return CheckResult("3", name, "INCONCLUSIVE",
                            "0 devices with >=2 owners in this bridged run -- nothing to check.")

    n_sharers_weight = RISK_WEIGHTS["n_sharers"]
    formula_mismatches = []
    buckets: dict[int, list] = {}
    for v in verdicts:
        n_sharers = int(round(v.metrics["n_sharers"]))
        expected_component = _clamp01((n_sharers - 1) / 3)
        actual_component = v.metrics.get("n_sharers_score")
        if actual_component is None or abs(actual_component - expected_component) > 1e-9:
            formula_mismatches.append((v.subject, n_sharers, expected_component, actual_component))
        buckets.setdefault(n_sharers, []).append(v)

    bucket_stats = []
    for n_sharers in sorted(buckets):
        vs = buckets[n_sharers]
        avg_score = statistics.mean(v.decision_score for v in vs)
        dist: dict[str, int] = {}
        for v in vs:
            dist[v.decision] = dist.get(v.decision, 0) + 1
        bucket_stats.append((n_sharers, len(vs), avg_score, dist))

    xs = [v.metrics["n_sharers"] for v in verdicts]
    ys = [v.decision_score for v in verdicts]
    r = _pearson_r(xs, ys)

    adequate_buckets = [b for b in bucket_stats if b[1] >= 5]
    enough_data = len(bucket_stats) >= 2 and len(adequate_buckets) >= 2

    bucket_lines = "; ".join(
        f"n_sharers={ns} (n={cnt}): avg decision_score={avg:.3f}, decisions={dist}"
        for ns, cnt, avg, dist in bucket_stats
    )

    if formula_mismatches:
        verdict = "DRIFT-DETECTED"
        mismatch_note = (
            f"{len(formula_mismatches)} device(s) where risk/scoring.py's own documented formula "
            f"(n_sharers_score = clamp((n_sharers-1)/3)) does NOT match the n_sharers_score actually "
            f"carried on the real AgentVerdict.metrics -- e.g. {formula_mismatches[:3]}."
        )
    elif not enough_data:
        verdict = "INCONCLUSIVE"
        mismatch_note = (
            f"formula check passed (every device's n_sharers_score component exactly matches "
            f"clamp((n_sharers-1)/3), weight={n_sharers_weight}) but only {len(adequate_buckets)}/"
            f"{len(bucket_stats)} n_sharers buckets have >=5 devices -- too few per bucket for a reliable "
            f"correlation verdict on the OVERALL decision_score (which also mixes in burst-based signals)."
        )
    elif r is not None and r < -0.05:
        verdict = "DRIFT-DETECTED"
        mismatch_note = (
            f"formula check passed, but the real correlation between n_sharers and decision_score across "
            f"all {len(verdicts)} scored devices is r={r:.3f} -- meaningfully NEGATIVE, i.e. more sharers "
            f"correlates with a LOWER score, the opposite of what risk/scoring.py's own positive "
            f"n_sharers weight ({n_sharers_weight}) structurally implies."
        )
    else:
        verdict = "MATCH"
        mismatch_note = (
            f"formula check passed for all {len(verdicts)} scored devices. Real correlation between "
            f"n_sharers and decision_score: r={r:.3f} (non-negative, the direction risk/scoring.py's own "
            f"positive n_sharers weight implies)."
        )

    detail = (
        f"Truman's device-sharing mechanism (world/engine.py's DEVICE_HOUSEHOLD_SHARING_FRACTION=0.3, "
        f"Simulation/docs/Memory.md's 'Device' section) produces real multi-owner devices grouped by "
        f"actual household membership (2-4 sharers, household size cap). Heimdall's own Risk scoring "
        f"(financial_system/risk/scoring.py) gives n_sharers a POSITIVE, deterministic component -- "
        f"n_sharers_score = clamp((n_sharers-1)/3), weight={n_sharers_weight} -- so a higher household-"
        f"driven sharing count should never LOWER a device's score, all else equal.\n"
        f"  per-bucket real numbers: {bucket_lines}\n"
        f"  {mismatch_note}\n"
        f"  Honest caveat (from Simulation/docs/Memory.md's own Device section): Truman deliberately has "
        f"NO fraud-ring mechanism, so the burst-based signals that carry {1 - n_sharers_weight:.0%} of "
        f"the total score weight are, by design, statistically unrelated to n_sharers here -- a weak or "
        f"near-zero net correlation on the full decision_score is the CORRECT, expected result, not a "
        f"gap; only a genuinely NEGATIVE correlation, or a formula mismatch, counts as drift."
    )
    return CheckResult("3", name, verdict, detail)


# ---------------------------------------------------------------------------
# Orchestration + report
# ---------------------------------------------------------------------------


@dataclass
class DriftDetectorRun:
    seed: int
    population: int
    days: int
    live_report: LiveLoopReport
    run: RunData
    start_date: datetime.date
    checks: list[CheckResult] = field(default_factory=list)
    batch_population: int | None = None
    batch_days: int | None = None


def run_checks_against_live_loop(
    live_report: LiveLoopReport, run: RunData, start_date: datetime.date,
    bridge_result: dict | None = None,
) -> list[CheckResult]:
    checks = [
        check_retry_timing_vs_payday_mechanism(live_report, run, start_date),
        check_decision_score_vs_realized_rate(live_report),
    ]
    if bridge_result is not None:
        checks.append(check_device_sharing_vs_risk_scoring(bridge_result))
    return checks


def run_drift_detector(
    *,
    seed: int,
    population: int,
    banks: int,
    merchants: int,
    days: int,
    start_date: datetime.date,
    live_work_dir: Path,
    batch_sim_outdir: Path | None = None,
    batch_bridge_dir: Path | None = None,
    batch_population: int = 500,
    batch_banks: int = 3,
    batch_merchants: int = 15,
    batch_days: int = 120,
) -> DriftDetectorRun:
    """Runs a real live-recovery-loop and (optionally, if batch_sim_outdir/
    batch_bridge_dir are given) a real batch bridge run, then computes all
    checks against the real output of both. Nothing here is mocked or
    replayed from a fixture -- every number the checks use comes from an
    actual run of `run_live_recovery_loop`/`run_bridge`/`run_simulation.run`,
    called unmodified."""
    live_report = run_live_recovery_loop(
        seed=seed, population=population, banks=banks, merchants=merchants,
        days=days, start_date=start_date, work_dir=live_work_dir,
    )
    run_data = RunData(str(Path(live_work_dir) / "sim_snapshot"))

    bridge_result = None
    if batch_sim_outdir is not None and batch_bridge_dir is not None:
        batch_sim_outdir = Path(batch_sim_outdir)
        batch_result = run_simulation.run(
            seed=seed, population=batch_population, banks=batch_banks,
            merchants=batch_merchants, days=batch_days, start_date=start_date,
            outdir=str(batch_sim_outdir),
        )
        del batch_result  # already written to batch_sim_outdir by run(); only the CSVs matter downstream
        bridge_result = run_bridge(batch_sim_outdir, Path(batch_bridge_dir))

    checks = run_checks_against_live_loop(live_report, run_data, start_date, bridge_result)

    return DriftDetectorRun(
        seed=seed, population=population, days=days, live_report=live_report,
        run=run_data, start_date=start_date, checks=checks,
        batch_population=(batch_population if bridge_result is not None else None),
        batch_days=(batch_days if bridge_result is not None else None),
    )


def build_report(result: DriftDetectorRun) -> str:
    lines: list[str] = []
    lines.append("# Heimdall <-> Truman Drift Detector")
    lines.append("")
    lines.append(
        "Checks whether Heimdall's real, live decisions (and their real, downstream effect on a "
        "running Truman world) are consistent with what Truman's OWN, known, documented mechanisms "
        "predict -- see financial_system/bridges/README.md's 'Drift detector' section for what each "
        "check means and why it's grounded in a specific, cited Truman mechanism, not a vibe score."
    )
    lines.append("")
    lines.append(f"- live-recovery-loop run: seed={result.seed} population={result.population} days={result.days}")
    lines.append(f"  checkpoints run: {result.live_report.checkpoints_run}")
    lines.append(f"  failed payments (total): {result.live_report.failed_payments_total}")
    lines.append(f"  Recovery decisions: {len(result.live_report.decisions)} {result.live_report.decision_counts}")
    lines.append(f"  retries scheduled: {len(result.live_report.retries_scheduled)}, "
                 f"attempted: {len(result.live_report.retries_attempted)}, "
                 f"succeeded: {result.live_report.retries_succeeded}")
    if result.batch_population is not None:
        lines.append(f"- batch bridge run (Check 3 only): population={result.batch_population} "
                     f"days={result.batch_days}")
    else:
        lines.append("- batch bridge run: NOT run this session -- Check 3 omitted")
    lines.append("")

    for c in result.checks:
        lines.append(f"## Check {c.check_id}: {c.name}")
        lines.append("")
        lines.append(f"**Verdict: {c.verdict}**")
        lines.append("")
        for para in c.detail.split("\n"):
            lines.append(para)
        lines.append("")

    lines.append("## Summary")
    lines.append("")
    counts: dict[str, int] = {}
    for c in result.checks:
        counts[c.verdict] = counts.get(c.verdict, 0) + 1
    lines.append(", ".join(f"{v}={n}" for v, n in sorted(counts.items())))
    lines.append("")

    return "\n".join(lines)


def _default_live_work_dir() -> Path:
    return Path(__file__).resolve().parent / "drift_detector_output" / "live"


def _default_batch_dir() -> Path:
    return Path(__file__).resolve().parent / "drift_detector_output" / "batch"


if __name__ == "__main__":
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Heimdall <-> Truman drift detector")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--population", type=int, default=20)
    parser.add_argument("--banks", type=int, default=2)
    parser.add_argument("--merchants", type=int, default=4)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--start-date", type=str, default="2026-01-01")
    parser.add_argument("--live-work-dir", type=str, default=str(_default_live_work_dir()))
    parser.add_argument("--skip-check3", action="store_true", help="Skip the batch-bridge-based Check 3")
    parser.add_argument("--batch-sim-outdir", type=str, default=str(_default_batch_dir() / "sim"))
    parser.add_argument("--batch-bridge-dir", type=str, default=str(_default_batch_dir() / "bridge"))
    parser.add_argument("--batch-population", type=int, default=500)
    parser.add_argument("--batch-banks", type=int, default=3)
    parser.add_argument("--batch-merchants", type=int, default=15)
    parser.add_argument("--batch-days", type=int, default=120)
    parser.add_argument("--save", type=str, default=None)
    args = parser.parse_args()

    t0 = time.time()
    result = run_drift_detector(
        seed=args.seed, population=args.population, banks=args.banks, merchants=args.merchants,
        days=args.days, start_date=datetime.date.fromisoformat(args.start_date),
        live_work_dir=Path(args.live_work_dir),
        batch_sim_outdir=(None if args.skip_check3 else Path(args.batch_sim_outdir)),
        batch_bridge_dir=(None if args.skip_check3 else Path(args.batch_bridge_dir)),
        batch_population=args.batch_population, batch_banks=args.batch_banks,
        batch_merchants=args.batch_merchants, batch_days=args.batch_days,
    )
    elapsed = time.time() - t0

    report_text = build_report(result)
    print(report_text)
    print(f"(wall-clock: {elapsed:.2f}s)")

    if args.save:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(report_text, encoding="utf-8")
        print(f"(saved to {save_path})", file=sys.stderr)
