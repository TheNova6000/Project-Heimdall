"""
Tests for the bridge's own new code (financial_system/bridges/). Does not
touch, import test fixtures from, or assert anything about
financial_system/'s existing scored phases -- those are exercised for real
by run_bridge.py against Heimdall's real recovery_agent, not re-tested here.

Run directly: `python -m financial_system.bridges.test_simulation_bridge`
or `pytest financial_system/bridges/test_simulation_bridge.py`
"""
from __future__ import annotations

import csv
import shutil
import tempfile
from pathlib import Path

from financial_system.bridges.simulation_bridge import (
    CURRENCY, SIMULATION_FAILURE_REASON, transform_simulation_output,
)

FIXTURE_DIR = Path(tempfile.mkdtemp(prefix="bridge_test_sim_"))


def _write(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _make_fixture_sim_output(tmp: Path) -> Path:
    """A tiny, hand-built Simulation/-shaped output directory, same column
    names as Simulation/output/sample/ (verified against a real run)."""
    sim_dir = tmp / "sim_out"
    sim_dir.mkdir(parents=True, exist_ok=True)

    _write(sim_dir / "persons.csv",
           ["person_id", "name", "income_monthly", "balance", "risk_preference", "payday"],
           [
               {"person_id": "person_00001", "name": "Person 1", "income_monthly": "5000",
                "balance": "1000", "risk_preference": "0.5", "payday": "1"},
               {"person_id": "person_00002", "name": "Person 2", "income_monthly": "3000",
                "balance": "50", "risk_preference": "0.9", "payday": "15"},
           ])
    _write(sim_dir / "merchants.csv",
           ["merchant_id", "name", "bank_account_id", "category", "balance"],
           [{"merchant_id": "merchant_0001", "name": "Merchant 1", "bank_account_id": "acct_000001",
             "category": "dining", "balance": "500"}])
    _write(sim_dir / "transactions.csv",
           ["transaction_id", "timestamp", "day", "from_id", "to_id", "amount", "kind", "balance_before"],
           [
               # a successful purchase
               {"transaction_id": "txn_1", "timestamp": "2026-01-01T10:00:00+00:00", "day": "0",
                "from_id": "person_00001", "to_id": "merchant_0001", "amount": "50.00",
                "kind": "purchase", "balance_before": "1000.00"},
               # a failed purchase (balance_before < amount, Simulation's one real failure cause)
               {"transaction_id": "txn_2", "timestamp": "2026-01-01T11:00:00+00:00", "day": "0",
                "from_id": "person_00002", "to_id": "merchant_0001", "amount": "80.00",
                "kind": "payment_failure", "balance_before": "50.00"},
               # non-purchase kinds that must be skipped entirely
               {"transaction_id": "txn_3", "timestamp": "2026-01-01T12:00:00+00:00", "day": "0",
                "from_id": "employer:person_00001", "to_id": "person_00001", "amount": "5000.00",
                "kind": "salary", "balance_before": "1000.00"},
               {"transaction_id": "txn_4", "timestamp": "2026-01-01T13:00:00+00:00", "day": "0",
                "from_id": "person_00001", "to_id": "person_00001", "amount": "100.00",
                "kind": "savings_sweep", "balance_before": "950.00"},
           ])
    return sim_dir


def test_transform_counts_and_skips():
    sim_dir = _make_fixture_sim_output(FIXTURE_DIR)
    out_dir = FIXTURE_DIR / "raw"
    report = transform_simulation_output(sim_dir, out_dir)

    assert report.persons_read == 2
    assert report.merchants_read == 1
    assert report.transactions_read == 4
    assert report.orders_written == 2       # only purchase + payment_failure
    assert report.payments_written == 2
    assert report.customers_written == 2
    assert report.devices_written == 2
    assert report.instruments_written == 2
    assert report.skipped_transaction_kinds == {"salary": 1, "savings_sweep": 1}
    print("test_transform_counts_and_skips: PASS")


def test_status_and_failure_reason_mapping():
    sim_dir = _make_fixture_sim_output(FIXTURE_DIR)
    out_dir = FIXTURE_DIR / "raw"
    transform_simulation_output(sim_dir, out_dir)

    with open(out_dir / "payments.csv", newline="", encoding="utf-8") as f:
        rows = {r["payment_id"]: r for r in csv.DictReader(f)}

    success_row = rows["pay_bridge_txn_1"]
    failed_row = rows["pay_bridge_txn_2"]

    assert success_row["status"] == "success"
    assert success_row["failure_reason"] == ""
    assert success_row["authorized_at"] and success_row["captured_at"]

    assert failed_row["status"] == "failed"
    assert failed_row["failure_reason"] == SIMULATION_FAILURE_REASON == "insufficient_funds"
    assert failed_row["authorized_at"] == "" and failed_row["captured_at"] == ""
    assert failed_row["currency"] == CURRENCY
    print("test_status_and_failure_reason_mapping: PASS")


def test_every_payment_has_own_order_1to1():
    """Mirrors the real financial_system/data/raw/ dataset's own convention
    (verified independently: 1000/1000 payments have order.amount ==
    payment.amount, one order per payment) -- this bridge reproduces the
    same convention rather than inventing a different one."""
    sim_dir = _make_fixture_sim_output(FIXTURE_DIR)
    out_dir = FIXTURE_DIR / "raw"
    transform_simulation_output(sim_dir, out_dir)

    with open(out_dir / "orders.csv", newline="", encoding="utf-8") as f:
        orders = {r["order_id"]: r for r in csv.DictReader(f)}
    with open(out_dir / "payments.csv", newline="", encoding="utf-8") as f:
        payments = list(csv.DictReader(f))

    order_ids_used = [p["order_id"] for p in payments]
    assert len(order_ids_used) == len(set(order_ids_used)), "each payment must have its own order"
    for p in payments:
        assert orders[p["order_id"]]["amount"] == p["amount"]
    print("test_every_payment_has_own_order_1to1: PASS")


def test_placeholder_device_and_instrument_are_flagged_and_one_per_person():
    sim_dir = _make_fixture_sim_output(FIXTURE_DIR)
    out_dir = FIXTURE_DIR / "raw"
    report = transform_simulation_output(sim_dir, out_dir)

    with open(out_dir / "devices.csv", newline="", encoding="utf-8") as f:
        devices = list(csv.DictReader(f))
    with open(out_dir / "payment_instruments.csv", newline="", encoding="utf-8") as f:
        instruments = list(csv.DictReader(f))

    assert len(devices) == 2 and len({d["device_id"] for d in devices}) == 2
    assert len(instruments) == 2 and len({i["instrument_id"] for i in instruments}) == 2
    assert any("carry zero signal" in f for f in report.fabricated_fields)
    print("test_placeholder_device_and_instrument_are_flagged_and_one_per_person: PASS")


def test_unmodeled_concepts_written_header_only():
    sim_dir = _make_fixture_sim_output(FIXTURE_DIR)
    out_dir = FIXTURE_DIR / "raw"
    transform_simulation_output(sim_dir, out_dir)

    for name in ("refunds.csv", "fees.csv", "settlements.csv", "settlement_payments.csv", "bank_transactions.csv"):
        with open(out_dir / name, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert rows == [], f"{name} should be header-only (Simulation/ does not model this concept)"
    print("test_unmodeled_concepts_written_header_only: PASS")


if __name__ == "__main__":
    try:
        test_transform_counts_and_skips()
        test_status_and_failure_reason_mapping()
        test_every_payment_has_own_order_1to1()
        test_placeholder_device_and_instrument_are_flagged_and_one_per_person()
        test_unmodeled_concepts_written_header_only()
        print("\nALL BRIDGE TESTS PASSED")
    finally:
        shutil.rmtree(FIXTURE_DIR, ignore_errors=True)
