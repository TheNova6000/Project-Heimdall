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
    names as Simulation/output/sample/ (verified against a real run) --
    including the Device columns added later (devices.csv,
    transactions.csv's device_id). Three persons: person_00001 and
    person_00003 share one device (dev_1, a household's "primary" device),
    person_00002 has their own (dev_2) -- exercises both the personal-device
    and shared-device paths in one fixture."""
    sim_dir = tmp / "sim_out"
    sim_dir.mkdir(parents=True, exist_ok=True)

    _write(sim_dir / "persons.csv",
           ["person_id", "name", "income_monthly", "balance", "risk_preference", "payday"],
           [
               {"person_id": "person_00001", "name": "Person 1", "income_monthly": "5000",
                "balance": "1000", "risk_preference": "0.5", "payday": "1"},
               {"person_id": "person_00002", "name": "Person 2", "income_monthly": "3000",
                "balance": "50", "risk_preference": "0.9", "payday": "15"},
               {"person_id": "person_00003", "name": "Person 3", "income_monthly": "4000",
                "balance": "800", "risk_preference": "0.3", "payday": "10"},
           ])
    _write(sim_dir / "merchants.csv",
           ["merchant_id", "name", "bank_account_id", "category", "balance"],
           [{"merchant_id": "merchant_0001", "name": "Merchant 1", "bank_account_id": "acct_000001",
             "category": "dining", "balance": "500"}])
    _write(sim_dir / "devices.csv",
           ["device_id", "owner_person_ids", "fingerprint"],
           [
               {"device_id": "dev_1", "owner_person_ids": '["person_00001", "person_00003"]',
                "fingerprint": "fp_dev_1"},
               {"device_id": "dev_2", "owner_person_ids": '["person_00002"]', "fingerprint": "fp_dev_2"},
           ])
    _write(sim_dir / "transactions.csv",
           ["transaction_id", "timestamp", "day", "from_id", "to_id", "amount", "kind", "balance_before",
            "device_id"],
           [
               # a successful purchase, from the shared device's primary owner
               {"transaction_id": "txn_1", "timestamp": "2026-01-01T10:00:00+00:00", "day": "0",
                "from_id": "person_00001", "to_id": "merchant_0001", "amount": "50.00",
                "kind": "purchase", "balance_before": "1000.00", "device_id": "dev_1"},
               # a failed purchase (balance_before < amount, Simulation's one real failure cause)
               {"transaction_id": "txn_2", "timestamp": "2026-01-01T11:00:00+00:00", "day": "0",
                "from_id": "person_00002", "to_id": "merchant_0001", "amount": "80.00",
                "kind": "payment_failure", "balance_before": "50.00", "device_id": "dev_2"},
               # a successful purchase from the OTHER sharer of the shared device
               {"transaction_id": "txn_5", "timestamp": "2026-01-01T14:00:00+00:00", "day": "0",
                "from_id": "person_00003", "to_id": "merchant_0001", "amount": "30.00",
                "kind": "purchase", "balance_before": "800.00", "device_id": "dev_1"},
               # non-purchase kinds that must be skipped entirely (device_id blank, as Simulation writes it)
               {"transaction_id": "txn_3", "timestamp": "2026-01-01T12:00:00+00:00", "day": "0",
                "from_id": "employer:person_00001", "to_id": "person_00001", "amount": "5000.00",
                "kind": "salary", "balance_before": "1000.00", "device_id": ""},
               {"transaction_id": "txn_4", "timestamp": "2026-01-01T13:00:00+00:00", "day": "0",
                "from_id": "person_00001", "to_id": "person_00001", "amount": "100.00",
                "kind": "savings_sweep", "balance_before": "950.00", "device_id": ""},
           ])
    return sim_dir


def test_transform_counts_and_skips():
    sim_dir = _make_fixture_sim_output(FIXTURE_DIR)
    out_dir = FIXTURE_DIR / "raw"
    report = transform_simulation_output(sim_dir, out_dir)

    assert report.persons_read == 3
    assert report.merchants_read == 1
    assert report.transactions_read == 5
    assert report.devices_read == 2
    assert report.orders_written == 3       # only purchase + payment_failure (txn_1, txn_2, txn_5)
    assert report.payments_written == 3
    assert report.customers_written == 3
    assert report.devices_written == 2      # real devices, direct from devices.csv
    assert report.shared_devices == 1       # dev_1, shared by person_00001 + person_00003
    assert report.instruments_written == 3  # one fabricated instrument per Person
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


def test_real_devices_and_fabricated_instruments():
    """Devices are now REAL, direct from Simulation/'s own devices.csv (not
    fabricated) -- payment_instruments remain a fabricated, flagged, thin
    1:1-per-person wrapper around the real device_id."""
    sim_dir = _make_fixture_sim_output(FIXTURE_DIR)
    out_dir = FIXTURE_DIR / "raw"
    report = transform_simulation_output(sim_dir, out_dir)

    with open(out_dir / "devices.csv", newline="", encoding="utf-8") as f:
        devices = list(csv.DictReader(f))
    with open(out_dir / "payment_instruments.csv", newline="", encoding="utf-8") as f:
        instruments = list(csv.DictReader(f))

    # Real device data, not the old dev_bridge_<person_id> placeholder shape.
    assert {d["device_id"] for d in devices} == {"dev_1", "dev_2"}
    assert len(instruments) == 3 and len({i["instrument_id"] for i in instruments}) == 3
    # Every instrument is traceable to the real device it wraps.
    by_customer = {i["customer_id"]: i for i in instruments}
    assert by_customer["person_00001"]["instrument_id"] == "instr_dev_1_person_00001"
    assert by_customer["person_00003"]["instrument_id"] == "instr_dev_1_person_00003"
    assert by_customer["person_00002"]["instrument_id"] == "instr_dev_2_person_00002"
    assert any("carries zero signal" in f for f in report.fabricated_fields)
    print("test_real_devices_and_fabricated_instruments: PASS")


def test_payments_reference_the_real_shared_device():
    """The whole point of this later addition: two different customers'
    payments both reference the SAME real device_id (dev_1) when they
    share a household device -- Risk's shared-device signal needs exactly
    this shape, and it must come from Simulation/'s real device_id column,
    not a fabricated per-person placeholder."""
    sim_dir = _make_fixture_sim_output(FIXTURE_DIR)
    out_dir = FIXTURE_DIR / "raw"
    transform_simulation_output(sim_dir, out_dir)

    with open(out_dir / "payments.csv", newline="", encoding="utf-8") as f:
        payments = {r["payment_id"]: r for r in csv.DictReader(f)}

    p1 = payments["pay_bridge_txn_1"]  # person_00001, dev_1
    p5 = payments["pay_bridge_txn_5"]  # person_00003, dev_1 (same device)
    p2 = payments["pay_bridge_txn_2"]  # person_00002, dev_2

    assert p1["device_id"] == p5["device_id"] == "dev_1"
    assert p1["customer_id"] != p5["customer_id"]
    assert p2["device_id"] == "dev_2"
    print("test_payments_reference_the_real_shared_device: PASS")


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
        test_real_devices_and_fabricated_instruments()
        test_payments_reference_the_real_shared_device()
        test_unmodeled_concepts_written_header_only()
        print("\nALL BRIDGE TESTS PASSED")
    finally:
        shutil.rmtree(FIXTURE_DIR, ignore_errors=True)
