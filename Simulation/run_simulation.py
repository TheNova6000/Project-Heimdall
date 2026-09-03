"""
Entry point for the Financial World Simulation (Phase 1).

Usage:
    python run_simulation.py --seed 42 --population 500 --days 90
    python run_simulation.py --seed 42 --population 500 --days 90 --outdir output/run_a

Writes one CSV per entity/event type into --outdir (default: output/),
matching Design.md's stated convention: lowercase, underscore-separated,
one file per type, not one giant combined file.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from world.engine import SimulationEngine, SimulationResult  # noqa: E402


def _write_csv(path: str, rows: list, fieldnames: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_output(result: SimulationResult, outdir: str) -> None:
    # persons.csv -- final state (balance reflects every simulated day's
    # activity; Bank.Account is the balance source of truth, see engine.py)
    person_balance = {}
    for account in result.accounts:
        if account.owner_type == "person":
            person_balance[account.owner_id] = account.balance

    person_rows = []
    for p in result.persons:
        row = dataclasses.asdict(p)
        row["balance"] = person_balance.get(p.person_id, p.balance)
        person_rows.append(row)
    _write_csv(
        os.path.join(outdir, "persons.csv"),
        person_rows,
        ["person_id", "name", "income_monthly", "balance", "risk_preference", "payday"],
    )

    bank_rows = [{"bank_id": b.bank_id, "name": b.name} for b in result.banks]
    _write_csv(os.path.join(outdir, "banks.csv"), bank_rows, ["bank_id", "name"])

    merchant_account_balance = {}
    for account in result.accounts:
        if account.owner_type == "merchant":
            merchant_account_balance[account.owner_id] = account.balance
    merchant_rows = []
    for m in result.merchants:
        merchant_rows.append(
            {
                "merchant_id": m.merchant_id,
                "name": m.name,
                "bank_account_id": m.bank_account_id,
                "category": m.category,
                "balance": merchant_account_balance.get(m.merchant_id, 0.0),
            }
        )
    _write_csv(
        os.path.join(outdir, "merchants.csv"),
        merchant_rows,
        ["merchant_id", "name", "bank_account_id", "category", "balance"],
    )

    account_rows = [
        {
            "account_id": a.account_id,
            "bank_id": a.bank_id,
            "owner_id": a.owner_id,
            "owner_type": a.owner_type,
            "balance": a.balance,
        }
        for a in result.accounts
    ]
    _write_csv(
        os.path.join(outdir, "accounts.csv"),
        account_rows,
        ["account_id", "bank_id", "owner_id", "owner_type", "balance"],
    )

    txn_rows = [dataclasses.asdict(t) for t in result.transactions]
    _write_csv(
        os.path.join(outdir, "transactions.csv"),
        txn_rows,
        ["transaction_id", "timestamp", "day", "from_id", "to_id", "amount", "kind", "balance_before"],
    )

    event_rows = [dataclasses.asdict(e) for e in result.events]
    _write_csv(
        os.path.join(outdir, "events.csv"),
        event_rows,
        ["event_id", "event_type", "subject_id", "occurred_at", "payload"],
    )


def run(
    seed: int,
    population: int,
    banks: int,
    merchants: int,
    days: int,
    start_date: datetime.date,
    outdir: str,
) -> SimulationResult:
    engine = SimulationEngine(
        seed=seed,
        num_persons=population,
        num_banks=banks,
        num_merchants=merchants,
        num_days=days,
        start_date=start_date,
    )
    result = engine.run()
    write_output(result, outdir)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Financial World Simulation (Phase 1)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (determinism, Rules.md #6)")
    parser.add_argument("--population", type=int, default=500, help="Number of Person agents")
    parser.add_argument("--banks", type=int, default=3, help="Number of Bank agents")
    parser.add_argument("--merchants", type=int, default=15, help="Number of Merchant agents")
    parser.add_argument("--days", type=int, default=90, help="Number of simulated days")
    parser.add_argument(
        "--start-date",
        type=str,
        default="2026-01-01",
        help="Simulated start date, YYYY-MM-DD",
    )
    parser.add_argument(
        "--outdir",
        type=str,
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "output"),
        help="Directory to write CSVs into",
    )
    args = parser.parse_args()

    start_date = datetime.date.fromisoformat(args.start_date)
    result = run(
        seed=args.seed,
        population=args.population,
        banks=args.banks,
        merchants=args.merchants,
        days=args.days,
        start_date=start_date,
        outdir=args.outdir,
    )

    print(
        f"Simulation complete: seed={args.seed} population={args.population} "
        f"banks={args.banks} merchants={args.merchants} days={args.days}"
    )
    print(f"  persons:      {len(result.persons)}")
    print(f"  transactions: {len(result.transactions)}")
    print(f"  events:       {len(result.events)}")
    print(f"Output written to: {args.outdir}")


if __name__ == "__main__":
    main()
