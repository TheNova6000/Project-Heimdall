"""
Tests for the Live Risk loop (live_risk_loop.py) -- the in-loop
device-blocking closure for the Risk domain (see this file's module
docstring and financial_system/bridges/README.md's "Live Risk loop"
section for the full design).

Two configurations, same rigor/reasoning as test_live_recovery_loop.py's
own "fast config" choice, adapted to Risk's own real requirement (a
REVIEW/HOLD verdict needs enough REAL accumulated device activity, unlike
Recovery's payment_failure which can happen on day 1):

- `_FAST_PARAMS` (population=30, days=10): cheap, real Heimdall Risk calls
  happen (several devices ARE already shared and scored), but no device
  has enough history yet to cross the REVIEW threshold -- used for the
  "is this really calling Heimdall, and never an LLM" tests, which don't
  need a block to have happened.
- `_BLOCK_PARAMS` (population=30, days=50): measured directly during this
  task's own development (see README.md's "Checkpoint frequency /
  population choice" section) to be the smallest days value at which
  device dev_00000d (seed=42) actually crosses into REVIEW AND at least
  one subsequent blocked purchase attempt is simulated (the block, decided
  from cumulative history through day <=48, protects day 49 onward -- day
  49 itself only exists in a run of >=50 days). ~60s per run -- used only
  by the tests that specifically need a real block to have happened.
"""
from __future__ import annotations

import csv
import datetime
import json
import shutil
from pathlib import Path

from financial_system.bridges.live_risk_loop import run_live_risk_loop

_WORK_ROOT = Path(__file__).resolve().parent / "_test_live_risk_loop_work"

_FAST_PARAMS = dict(seed=42, population=30, banks=2, merchants=4, days=10,
                     start_date=datetime.date(2026, 1, 1))
_BLOCK_PARAMS = dict(seed=42, population=30, banks=2, merchants=4, days=50,
                      start_date=datetime.date(2026, 1, 1))


def _run(work_subdir: str, **overrides):
    params = dict(_FAST_PARAMS)
    params.update(overrides)
    work_dir = _WORK_ROOT / work_subdir
    if work_dir.exists():
        shutil.rmtree(work_dir)
    return run_live_risk_loop(work_dir=work_dir, **params)


# One real block-config run, cached and reused across every test that just
# needs "a real block happened" -- NOT reused by the determinism test,
# which by definition needs two INDEPENDENT fresh runs. Keeps total suite
# wall-clock bounded (~60s for this one run, shared by several assertions,
# rather than paying it repeatedly).
_block_cache: dict = {}


def _block_run():
    if "report" not in _block_cache:
        work_dir = _WORK_ROOT / "block_shared"
        if work_dir.exists():
            shutil.rmtree(work_dir)
        _block_cache["report"] = run_live_risk_loop(work_dir=work_dir, **_BLOCK_PARAMS)
        _block_cache["work_dir"] = work_dir
    return _block_cache["report"], _block_cache["work_dir"]


def test_risk_is_real_not_mocked():
    """
    Every decision must carry Heimdall's real, unmodified
    risk/risk_agent.py `_TIER_DECISION` mapping (RELEASE/REVIEW/HOLD, never
    an invented value), and every RELEASE decision's score must be < 0.3
    (risk/scoring.py's own real MEDIUM_THRESHOLD) -- numbers a stub/mock
    would have no reason to reproduce.
    """
    report = _run("real_not_mocked")
    assert len(report.decisions) > 0, "expected at least one real Risk decision in this deterministic run"
    for d in report.decisions:
        assert d.decision in ("RELEASE", "REVIEW", "HOLD")
        if d.decision == "RELEASE":
            assert d.decision_score < 0.3
        assert d.n_sharers >= 2, "devices_with_sharers() only ever returns >=2-owner devices"
        assert len(d.sharer_customer_ids) == d.n_sharers
        # See RiskDecisionRecord's own docstring: only non-None if
        # investigate_evidence() (Discovery.AI/LLM) actually ran.
        assert d.investigation_confidence is None


def test_no_llm_calls_ever():
    """
    Zero LLM/Discovery.AI calls anywhere in this loop -- confirmed two ways:
    (1) live_risk_loop.py's only call site passes investigate=False
    unconditionally (read the source); (2) every real decision's
    investigation_confidence is None, which risk_agent.py's own code only
    ever sets when investigate_evidence() actually executed (which itself
    requires BOTH investigate=True AND tier=="HIGH" -- neither ever holds
    here). Both must hold.
    """
    report = _run("no_llm")
    assert len(report.decisions) > 0
    assert all(d.investigation_confidence is None for d in report.decisions)


def test_block_actually_prevents_a_real_purchase():
    """
    THE mechanical-consequence proof this task exists to demonstrate: a
    REVIEW/HOLD verdict must have led to a real block_device() call, and at
    least one subsequent purchase attempt from that device must have been
    mechanically prevented -- not merely logged. `would_have_succeeded`
    (balance_before >= amount, world/agents/bank.py's own real
    post_transfer() enforcement rule) must be True for at least one
    prevented attempt, proving the block was genuinely consequential (money
    that would have moved, didn't), not a no-op blocking of an attempt that
    would have failed anyway.
    """
    report, _ = _block_run()
    assert len(report.devices_blocked) >= 1, "expected at least one real REVIEW/HOLD-driven block in this run"
    assert any(d.decision in ("REVIEW", "HOLD") for d in report.decisions)
    assert len(report.blocked_purchase_attempts) >= 1, (
        "expected at least one real purchase attempt mechanically prevented by a block"
    )
    assert any(a.would_have_succeeded for a in report.blocked_purchase_attempts), (
        "expected at least one prevented attempt that would have succeeded (balance_before >= amount) -- "
        "otherwise the block's real effect can't be distinguished from a no-op"
    )
    # Every blocked attempt's device must be one this run actually blocked.
    for a in report.blocked_purchase_attempts:
        assert a.device_id in report.devices_blocked


def test_blocked_purchase_is_recorded_honestly_via_payload_not_new_kind():
    """
    A device-blocked purchase failure reuses Transaction kind=
    "payment_failure" (Heimdall's own real FAILURE_TAXONOMY already names
    a `risk_block` category for exactly this situation -- see engine.py's
    _maybe_attempt_purchase() comment) with a distinct event_type
    (purchase_blocked_device, never purchase_failed) and a
    `blocked_device: true` Event payload marker (retried_from's own
    precedent) -- never a new Transaction CSV column, and never silently
    indistinguishable from an ordinary insufficient-funds failure at the
    Event layer.
    """
    report, work_dir = _block_run()
    assert len(report.blocked_purchase_attempts) >= 1

    txns_path = work_dir / "sim_snapshot" / "transactions.csv"
    events_path = work_dir / "sim_snapshot" / "events.csv"

    with open(txns_path, newline="", encoding="utf-8") as f:
        txn_rows = {r["transaction_id"]: r for r in csv.DictReader(f)}
    with open(events_path, newline="", encoding="utf-8") as f:
        event_rows = list(csv.DictReader(f))

    blocked_txn_ids = {a.transaction_id for a in report.blocked_purchase_attempts}
    for txn_id in blocked_txn_ids:
        assert txn_rows[txn_id]["kind"] == "payment_failure"

    blocked_events = [e for e in event_rows if e["event_type"] == "purchase_blocked_device"]
    assert len(blocked_events) == len(report.blocked_purchase_attempts)
    for e in blocked_events:
        payload = json.loads(e["payload"])
        assert payload["blocked_device"] is True
        assert payload["transaction_id"] in blocked_txn_ids

    # A device_blocked state-change Event exists for every device this run blocked.
    device_blocked_events = [e for e in event_rows if e["event_type"] == "device_blocked"]
    assert {e["subject_id"] for e in device_blocked_events} == set(report.devices_blocked)


def test_determinism_two_runs_identical_reports():
    """
    Same seed + same config -> byte-identical report content: same devices
    scored, same decisions/scores, same devices blocked (and on what day),
    same blocked purchase attempts -- across two completely independent
    runs of the loop (population=30/days=50, the block-config -- proves
    determinism of the actual blocking mechanic, not just the decisions).
    """
    r1 = run_live_risk_loop(work_dir=_WORK_ROOT / "det_a", **_BLOCK_PARAMS)
    r2 = run_live_risk_loop(work_dir=_WORK_ROOT / "det_b", **_BLOCK_PARAMS)

    assert r1.decisions == r2.decisions
    assert r1.devices_blocked == r2.devices_blocked
    assert r1.blocked_purchase_attempts == r2.blocked_purchase_attempts
    assert r1.total_transactions_final == r2.total_transactions_final
    assert r1.devices_with_sharers_total == r2.devices_with_sharers_total
    assert r1.checkpoints_run == r2.checkpoints_run


def test_determinism_two_runs_byte_identical_world_output():
    """
    The strongest form of the determinism guarantee: the actual CSV bytes
    of the final world snapshot (transactions.csv, events.csv, persons.csv)
    are byte-for-byte identical across two independent runs of the same
    seed/config, including every device_blocked/purchase_blocked_device
    row and payload.
    """
    work_a = _WORK_ROOT / "bytes_a"
    work_b = _WORK_ROOT / "bytes_b"
    run_live_risk_loop(work_dir=work_a, **_BLOCK_PARAMS)
    run_live_risk_loop(work_dir=work_b, **_BLOCK_PARAMS)

    for fname in ("transactions.csv", "events.csv", "persons.csv", "devices.csv"):
        a = (work_a / "sim_snapshot" / fname).read_bytes()
        b = (work_b / "sim_snapshot" / fname).read_bytes()
        assert a == b, f"{fname} differs between two identical-seed live-risk-loop runs"


def test_default_run_engine_flow_unaffected_by_blocked_devices_set():
    """
    Sanity check on the "no-op by default" guarantee from the OTHER
    direction: a plain SimulationEngine (no live-risk-loop involvement at
    all -- block_device() never called) has an empty `blocked_devices` set
    and produces zero `purchase_blocked_device`/`device_blocked` events,
    for the exact same seed/population/days the block-config above uses.
    This is the engine-level counterfactual the README's causal-effect
    trace is built on: the two runs are byte-identical up to the day the
    live loop's first block takes effect, and the live loop's own
    blocked-purchase transaction_ids/balances exactly match this plain
    run's corresponding (unblocked, successful) transactions up to that
    point -- see README.md's "Real, traced causal effect" section for the
    full concrete numbers this proves.
    """
    import sys
    sim_dir = Path(__file__).resolve().parent.parent.parent / "Simulation"
    if str(sim_dir) not in sys.path:
        sys.path.insert(0, str(sim_dir))
    from world.engine import SimulationEngine  # noqa: E402

    engine = SimulationEngine(seed=_BLOCK_PARAMS["seed"], num_persons=_BLOCK_PARAMS["population"],
                               num_banks=_BLOCK_PARAMS["banks"], num_merchants=_BLOCK_PARAMS["merchants"],
                               num_days=_BLOCK_PARAMS["days"], start_date=_BLOCK_PARAMS["start_date"])
    assert engine.blocked_devices == set()
    engine.run()
    assert engine.blocked_devices == set(), "run() must never populate blocked_devices on its own"
    assert not any(e.event_type in ("purchase_blocked_device", "device_blocked") for e in engine.events)

    # Cross-check against the real live-loop run: identical transaction
    # history for the blocked device's owners up to (and including) the
    # last day BEFORE the block took effect.
    report, _ = _block_run()
    first_blocked_day = min(a.day for a in report.blocked_purchase_attempts)
    blocked_device_id = report.blocked_purchase_attempts[0].device_id
    owners = {pid for pid, did in engine.person_device.items() if did == blocked_device_id}

    plain_txns = sorted(
        (t.transaction_id, t.from_id, t.kind, round(t.amount, 2), round(t.balance_before, 2))
        for t in engine.transactions
        if t.from_id in owners and t.kind in ("purchase", "payment_failure") and t.day < first_blocked_day
    )
    # Re-derive the SAME slice from the live loop's own final snapshot.
    txns_path = _block_cache["work_dir"] / "sim_snapshot" / "transactions.csv"
    with open(txns_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    live_txns = sorted(
        (r["transaction_id"], r["from_id"], r["kind"], round(float(r["amount"]), 2), round(float(r["balance_before"]), 2))
        for r in rows
        if r["from_id"] in owners and r["kind"] in ("purchase", "payment_failure") and int(r["day"]) < first_blocked_day
    )
    assert plain_txns == live_txns, (
        "the plain (never-blocked) run and the live-risk-loop run must have IDENTICAL transaction "
        "history for the blocked device's owners up to the day before the block took effect -- a real, "
        "checkable proof that the two worlds only diverge from the block point onward, not before it"
    )


def teardown_module(module):
    if _WORK_ROOT.exists():
        shutil.rmtree(_WORK_ROOT, ignore_errors=True)
