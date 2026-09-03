"""
Sampling/loading utilities + CLI entry point for the validation system
(this task's "Part B"). See docs/Memory.md's "Phase 2.5" section for the
full design writeup and docs/Rules.md #1/#3 (this is statistical
comparison against CSV output -- no LLM, no external dataset download; it
only reads a run's own already-generated output files).

This module is the CLI entry point (mirrors stats/report.py's own
combined logic+CLI style, and this task's own example command):

    python validation/sample.py --outdir output/some_run \
        --save output/some_run/validation_report.md

`validation/report.py` holds the actual B.1/B.2 check logic and
`build_report()`; this module's job is (a) loading a run's CSV output,
(b) optionally sampling persons down to a manageable size for the
per-person checks (savings/household/spend-ratio) on a very large run,
and (c) the argparse CLI, matching Design.md's "plain text or Markdown,
printed to console and optionally saved to a file" convention.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class RunData:
    """
    Everything the validation checks need, read once from a run's output
    directory. Numeric fields are coerced to float/int at load time so
    check functions don't each have to re-parse strings.
    """

    def __init__(self, outdir: str):
        self.outdir = outdir

        self.persons = _read_csv(os.path.join(outdir, "persons.csv"))
        for row in self.persons:
            row["income_monthly"] = float(row["income_monthly"])
            row["balance"] = float(row["balance"])
            row["risk_preference"] = float(row["risk_preference"])
            row["payday"] = int(row["payday"])

        self.accounts = _read_csv(os.path.join(outdir, "accounts.csv"))
        for row in self.accounts:
            row["balance"] = float(row["balance"])

        self.transactions = _read_csv(os.path.join(outdir, "transactions.csv"))
        for row in self.transactions:
            row["amount"] = float(row["amount"])
            row["balance_before"] = float(row["balance_before"])
            row["day"] = int(row["day"])

        self.ledger_entries = _read_csv(os.path.join(outdir, "ledger_entries.csv"))
        for row in self.ledger_entries:
            row["amount"] = float(row["amount"])
            row["balance_after"] = float(row["balance_after"])

        self.households = _read_csv(os.path.join(outdir, "households.csv"))
        self.organizations = _read_csv(os.path.join(outdir, "organizations.csv"))
        for row in self.organizations:
            row["num_employees"] = int(row["num_employees"])
            row["balance"] = float(row["balance"])

        self.communities = _read_csv(os.path.join(outdir, "communities.csv"))

    @property
    def person_ids(self) -> list[str]:
        return [p["person_id"] for p in self.persons]


def sample_person_ids(run: RunData, sample_size: int | None, seed: int) -> set[str]:
    """
    A deterministic (given `seed`) subset of person_ids to use for the
    per-person checks (savings/household accumulation, spend/income
    ratio). `sample_size=None` or >= population uses everyone -- sampling
    only matters for keeping per-person checks fast/manageable against a
    very large run; it draws from a SEPARATE random.Random instance from
    this validation module (never the simulation's own seeded RNG, so
    validating a run never perturbs or depends on how that run itself was
    generated).
    """
    ids = run.person_ids
    if sample_size is None or sample_size >= len(ids):
        return set(ids)
    rng = random.Random(seed)
    return set(rng.sample(ids, sample_size))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate a Financial World Simulation run's output: internal mechanism "
        "consistency (B.1) and comparison against docs/Research.md's cited real-world "
        "numbers (B.2)."
    )
    parser.add_argument(
        "--outdir",
        type=str,
        required=True,
        help="Directory containing a completed run's CSV output (persons.csv, "
        "transactions.csv, etc.)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Optional cap on how many persons the per-person checks (savings/household "
        "accumulation, spend/income ratio) sample. Default: use the whole population.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=12345,
        help="Seed for THIS validation run's own sampling RNG (independent of the "
        "simulation run being validated) -- default 12345, arbitrary but fixed so "
        "re-running validation against the same --outdir with the same --sample-size "
        "reproduces the same sample.",
    )
    parser.add_argument("--save", type=str, default=None, help="Optional path to save the report as Markdown")
    args = parser.parse_args()

    # Imported here (not at module top) so `python validation/sample.py --help`
    # doesn't require the report module's own imports to succeed first --
    # matches this file's role as the thin CLI wrapper.
    from validation.report import build_report

    report = build_report(args.outdir, sample_size=args.sample_size, seed=args.seed)
    print(report)

    if args.save:
        os.makedirs(os.path.dirname(os.path.abspath(args.save)), exist_ok=True)
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n(saved to {args.save})", file=sys.stderr)


if __name__ == "__main__":
    main()
