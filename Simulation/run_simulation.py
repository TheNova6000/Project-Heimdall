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
import json
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

    # Phase 2.5: reverse lookups so persons.csv can show which Household/
    # Organization (if any) each person belongs to, without storing those
    # ids on the Person dataclass itself (Person's fields stay exactly
    # Architecture.md's data model -- household_id/organization_id are
    # auxiliary output-layer metadata, computed here from Household.
    # person_ids / Organization.employee_person_ids, not carried by the
    # agent). Empty string, not missing, when a person belongs to neither.
    household_by_person = {pid: h.household_id for h in result.households for pid in h.person_ids}
    organization_by_person = {
        pid: o.organization_id for o in result.organizations for pid in o.employee_person_ids
    }

    person_rows = []
    for p in result.persons:
        row = dataclasses.asdict(p)
        row["balance"] = person_balance.get(p.person_id, p.balance)
        row["household_id"] = household_by_person.get(p.person_id, "")
        row["organization_id"] = organization_by_person.get(p.person_id, "")
        person_rows.append(row)
    _write_csv(
        os.path.join(outdir, "persons.csv"),
        person_rows,
        [
            "person_id",
            "name",
            "income_monthly",
            "balance",
            "risk_preference",
            "payday",
            "household_id",
            "organization_id",
        ],
    )

    bank_rows = [{"bank_id": b.bank_id, "name": b.name} for b in result.banks]
    _write_csv(os.path.join(outdir, "banks.csv"), bank_rows, ["bank_id", "name"])

    merchant_account_balance = {}
    merchant_pending_balance = {}
    for account in result.accounts:
        if account.owner_type == "merchant":
            merchant_account_balance[account.owner_id] = account.balance
        elif account.owner_type == "merchant_pending":
            # Phase 2: funds received but not yet settled (see
            # world/engine.py's _run_settlement) -- surfaced as its own
            # column so "received vs. settled" is visible directly in
            # merchants.csv, not just derivable from accounts.csv.
            merchant_pending_balance[account.owner_id] = account.balance
    merchant_rows = []
    for m in result.merchants:
        merchant_rows.append(
            {
                "merchant_id": m.merchant_id,
                "name": m.name,
                "bank_account_id": m.bank_account_id,
                "category": m.category,
                "balance": merchant_account_balance.get(m.merchant_id, 0.0),
                "pending_account_id": m.pending_account_id,
                "pending_balance": merchant_pending_balance.get(m.merchant_id, 0.0),
            }
        )
    _write_csv(
        os.path.join(outdir, "merchants.csv"),
        merchant_rows,
        [
            "merchant_id",
            "name",
            "bank_account_id",
            "category",
            "balance",
            "pending_account_id",
            "pending_balance",
        ],
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

    # Phase 2: the double-entry ledger itself, flattened across every
    # account in every bank -- one row per LedgerEntry, sorted by
    # entry_id. entry_id is a monotonic counter (world/engine.py's
    # _IdCounters), so sorting by it recovers the exact global posting
    # order deterministically, the same way transaction_id/event_id
    # already do for their own CSVs.
    ledger_rows = [
        dataclasses.asdict(entry)
        for account in sorted(result.accounts, key=lambda a: a.account_id)
        for entry in account.ledger
    ]
    ledger_rows.sort(key=lambda r: r["entry_id"])
    _write_csv(
        os.path.join(outdir, "ledger_entries.csv"),
        ledger_rows,
        [
            "entry_id",
            "account_id",
            "timestamp",
            "entry_type",
            "amount",
            "balance_after",
            "description",
            "transaction_id",
        ],
    )

    # Phase 2.5: households.csv / organizations.csv / communities.csv --
    # one file per new entity type, matching Design.md's existing
    # "lowercase, underscore-separated, one file per entity type"
    # convention. member-id lists use a JSON array string, same convention
    # as events.csv's `payload` column (Design.md: "JSON only where a
    # record's shape is genuinely nested... a flat CSV would lose
    # information" -- a variable-length id list is exactly that case).
    household_account_balance = {
        a.owner_id: a.balance for a in result.accounts if a.owner_type == "household"
    }
    household_rows = [
        {
            "household_id": h.household_id,
            "person_ids": json.dumps(h.person_ids),
            "household_account_id": h.household_account_id,
            "balance": household_account_balance.get(h.household_id, 0.0),
        }
        for h in result.households
    ]
    _write_csv(
        os.path.join(outdir, "households.csv"),
        household_rows,
        ["household_id", "person_ids", "household_account_id", "balance"],
    )

    org_revenue_balance = {
        a.owner_id: a.balance for a in result.accounts if a.owner_type == "organization_revenue"
    }
    organization_rows = [
        {
            "organization_id": o.organization_id,
            "name": o.name,
            "employee_person_ids": json.dumps(o.employee_person_ids),
            "num_employees": len(o.employee_person_ids),
            "revenue_account_id": o.revenue_account_id,
            "balance": org_revenue_balance.get(o.organization_id, 0.0),
        }
        for o in result.organizations
    ]
    _write_csv(
        os.path.join(outdir, "organizations.csv"),
        organization_rows,
        [
            "organization_id",
            "name",
            "employee_person_ids",
            "num_employees",
            "revenue_account_id",
            "balance",
        ],
    )

    community_rows = [
        {
            "community_id": c.community_id,
            "household_ids": json.dumps(c.household_ids),
            "organization_ids": json.dumps(c.organization_ids),
        }
        for c in result.communities
    ]
    _write_csv(
        os.path.join(outdir, "communities.csv"),
        community_rows,
        ["community_id", "household_ids", "organization_ids"],
    )

    txn_rows = [dataclasses.asdict(t) for t in result.transactions]
    _write_csv(
        os.path.join(outdir, "transactions.csv"),
        txn_rows,
        [
            "transaction_id",
            "timestamp",
            "day",
            "from_id",
            "to_id",
            "amount",
            "kind",
            "balance_before",
            "device_id",
        ],
    )

    # Device: one row per Device (device_id, its owning person_id(s) -- one
    # or more if this is a household's shared "primary" device, otherwise
    # exactly one -- and a fingerprint-equivalent field). owner_person_ids
    # uses the same JSON-array-string convention as households.csv's
    # person_ids / communities.csv's id lists (Design.md: "JSON only where
    # a record's shape is genuinely nested"). issued_day/expiry_day (Phase
    # 3, "Mechanism Engine" -- see docs/Memory.md's "Phase 3" section) are
    # new, additive columns -- simulated-day indices, same convention as
    # transactions.csv's own `day` column.
    device_rows = [
        {
            "device_id": d.device_id,
            "owner_person_ids": json.dumps(d.owner_person_ids),
            "fingerprint": d.fingerprint,
            "issued_day": d.issued_day,
            "expiry_day": d.expiry_day,
        }
        for d in result.devices
    ]
    _write_csv(
        os.path.join(outdir, "devices.csv"),
        device_rows,
        ["device_id", "owner_person_ids", "fingerprint", "issued_day", "expiry_day"],
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
