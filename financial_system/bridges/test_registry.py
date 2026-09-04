"""
Tests for the domain bridge registry (financial_system/bridges/registry.py,
capability_report.py, coverage_check.py). Does not touch, import fixtures
from, or assert anything about financial_system/'s existing scored phases --
those stay exercised for real by run_bridge.py / test_simulation_bridge.py,
unchanged, same boundary as before.

Run directly: `python -m financial_system.bridges.test_registry`
or `pytest financial_system/bridges/test_registry.py`
"""
from __future__ import annotations

import csv
import inspect
import shutil
import tempfile
from pathlib import Path

from financial_system.bridges import capability_report  # noqa: F401 -- registers "coverage" on import
from financial_system.bridges.coverage_check import compute_settlement_coverage
from financial_system.bridges.registry import (
    DOMAIN_REGISTRY, DomainBridge, bridged_domains, blocked_domains, get_domain, register_domain,
)
from financial_system.bridges.simulation_bridge import transform_simulation_output

EXPECTED_BRIDGED = {"recovery", "risk", "controller", "coverage"}
EXPECTED_BLOCKED = {"fraud", "credit", "loan"}


def test_all_six_real_domains_present_with_correct_status():
    # "all 6 domains" per the task = the 3 bridged + 3 blocked real ones;
    # "coverage" is the separate, 7th, demonstration-only entry proving
    # extensibility (registered by importing capability_report above).
    core_six = {"recovery", "risk", "controller", "fraud", "credit", "loan"}
    assert core_six <= set(DOMAIN_REGISTRY.keys())
    for name in ("recovery", "risk", "controller"):
        assert get_domain(name).status == "BRIDGED"
    for name in ("fraud", "credit", "loan"):
        assert get_domain(name).status == "BLOCKED"
    print("test_all_six_real_domains_present_with_correct_status: PASS")


def test_coverage_domain_registered_by_capability_report():
    """Proves the mechanism: capability_report.py, a module that only
    imports registry.py's public API, successfully registered a brand-new
    7th domain ("coverage") purely by calling register_domain() -- this
    was NOT baked into registry.py's own static six."""
    assert "coverage" in DOMAIN_REGISTRY
    entry = get_domain("coverage")
    assert entry.status == "BRIDGED"
    assert entry.transform_fn is compute_settlement_coverage
    print("test_coverage_domain_registered_by_capability_report: PASS")


def test_bridged_and_blocked_partition_the_registry():
    bridged_names = {d.domain_name for d in bridged_domains()}
    blocked_names = {d.domain_name for d in blocked_domains()}
    assert bridged_names == EXPECTED_BRIDGED
    assert blocked_names == EXPECTED_BLOCKED
    assert bridged_names.isdisjoint(blocked_names)
    print("test_bridged_and_blocked_partition_the_registry: PASS")


def test_domain_bridge_validates_status_field_combinations():
    # A BRIDGED entry without a transform_fn must be rejected.
    try:
        DomainBridge(
            domain_name="bad_bridged", status="BRIDGED",
            heimdall_entry_point="x", required_truman_fields=["y"], last_verified="z",
        )
        raise AssertionError("expected ValueError for BRIDGED entry with no transform_fn")
    except ValueError:
        pass

    # A BLOCKED entry without a blocked_reason must be rejected.
    try:
        DomainBridge(
            domain_name="bad_blocked", status="BLOCKED",
            heimdall_entry_point="x", required_truman_fields=["y"], last_verified="z",
        )
        raise AssertionError("expected ValueError for BLOCKED entry with no blocked_reason")
    except ValueError:
        pass

    print("test_domain_bridge_validates_status_field_combinations: PASS")


def test_register_domain_refuses_silent_overwrite():
    dummy = DomainBridge(
        domain_name="__test_dummy__", status="BLOCKED",
        heimdall_entry_point="does not exist yet -- test fixture only",
        required_truman_fields=["a test-only field that does not correspond to any real Truman output"],
        blocked_reason="test fixture, not a real domain -- exists only to prove register_domain() works",
        last_verified="test_registry.py::test_register_domain_refuses_silent_overwrite",
    )
    register_domain(dummy)
    try:
        register_domain(dummy)
        raise AssertionError("expected ValueError on duplicate registration without replace=True")
    except ValueError:
        pass
    # replace=True must succeed.
    register_domain(dummy, replace=True)
    assert get_domain("__test_dummy__") is dummy
    del DOMAIN_REGISTRY["__test_dummy__"]  # clean up so it doesn't pollute other tests/the real report
    print("test_register_domain_refuses_silent_overwrite: PASS")


def test_synthetic_dummy_domain_shows_up_in_capability_report():
    """Validates the registry's extensibility a second, independent way
    (per the task's own fallback option): register a synthetic/test-only
    dummy domain and confirm the capability report correctly lists it."""
    dummy = DomainBridge(
        domain_name="__test_synthetic_domain__", status="BLOCKED",
        heimdall_entry_point="does not exist yet -- synthetic test fixture",
        required_truman_fields=["a synthetic field invented purely for this test"],
        blocked_reason="synthetic test-only domain, not a real Heimdall capability",
        last_verified="test_registry.py::test_synthetic_dummy_domain_shows_up_in_capability_report",
    )
    register_domain(dummy)
    try:
        report = capability_report.build_report()
        assert "__test_synthetic_domain__" in report
        assert "synthetic test-only domain, not a real Heimdall capability" in report
    finally:
        del DOMAIN_REGISTRY["__test_synthetic_domain__"]
    print("test_synthetic_dummy_domain_shows_up_in_capability_report: PASS")


def test_bridged_required_fields_match_what_the_real_transform_reads():
    """The task's own required check: a BRIDGED domain's declared
    required_truman_fields must actually match what its real transform
    reads. Verified structurally (the transform's own source references
    every raw column/file this registry claims for each domain) rather
    than by re-deriving field lists from scratch -- the exact same
    grounding rule the task set for writing these fields in the first
    place: extracted from the real code, not invented."""
    # Whole-module source, not just the function body: SIMULATION_FAILURE_REASON
    # ("insufficient_funds") is a module-level constant the function
    # references by name, not a literal repeated inside the function itself.
    src = inspect.getsource(inspect.getmodule(transform_simulation_output))

    recovery = get_domain("recovery")
    for token in ("kind", "payment_failure", "insufficient_funds", "failure_reason", "status"):
        assert token in src, f"recovery's required field mentions {token!r}, not found in real transform"
    assert any("failure_reason" in f for f in recovery.required_truman_fields)
    assert any("status" in f for f in recovery.required_truman_fields)

    risk = get_domain("risk")
    for token in ("devices.csv", "device_id", "owner_person_ids", "fingerprint"):
        assert token in src, f"risk's required field mentions {token!r}, not found in real transform"
    assert any("device_id" in f for f in risk.required_truman_fields)
    assert any("owner_person_ids" in f for f in risk.required_truman_fields)

    controller = get_domain("controller")
    for token in ("settlement", "settlement_payments", "net_amount", "bank_transactions"):
        assert token in src, f"controller's required field mentions {token!r}, not found in real transform"
    assert any("settlement" in f for f in controller.required_truman_fields)
    assert any("settlement_payments.csv" in f for f in controller.required_truman_fields)

    print("test_bridged_required_fields_match_what_the_real_transform_reads: PASS")


def test_coverage_transform_produces_real_output_on_a_fixture():
    """The coverage domain must actually run and produce real numbers, not
    be a documentation-only stub -- exercised here against a tiny, hand-
    built bridge-output-shaped fixture (mirrors test_simulation_bridge.py's
    fixture pattern rather than requiring a full Simulation/ run)."""
    tmp = Path(tempfile.mkdtemp(prefix="coverage_test_"))
    try:
        with open(tmp / "payments.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["payment_id", "status"])
            w.writeheader()
            w.writerow({"payment_id": "pay_1", "status": "success"})
            w.writerow({"payment_id": "pay_2", "status": "success"})
            w.writerow({"payment_id": "pay_3", "status": "failed"})
        with open(tmp / "settlement_payments.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["settlement_id", "payment_id"])
            w.writeheader()
            w.writerow({"settlement_id": "settle_1", "payment_id": "pay_1"})

        report = compute_settlement_coverage(tmp)
        assert report.successful_payments == 2
        assert report.payments_covered_by_a_settlement == 1
        assert report.coverage_rate == 0.5
        print("test_coverage_transform_produces_real_output_on_a_fixture: PASS")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_capability_report_runs_and_produces_real_output():
    report = capability_report.build_report()
    assert "=== Heimdall Domain Bridge Registry" in report
    for name in ("recovery", "risk", "controller", "coverage"):
        assert name in report
    for name in ("fraud", "credit", "loan"):
        assert name in report
        assert "Blocked reason:" in report
    print("test_capability_report_runs_and_produces_real_output: PASS")


if __name__ == "__main__":
    test_all_six_real_domains_present_with_correct_status()
    test_coverage_domain_registered_by_capability_report()
    test_bridged_and_blocked_partition_the_registry()
    test_domain_bridge_validates_status_field_combinations()
    test_register_domain_refuses_silent_overwrite()
    test_synthetic_dummy_domain_shows_up_in_capability_report()
    test_bridged_required_fields_match_what_the_real_transform_reads()
    test_coverage_transform_produces_real_output_on_a_fixture()
    test_capability_report_runs_and_produces_real_output()
    print("\nALL REGISTRY TESTS PASSED")
