"""
Device tests -- the new entity/mechanism this task added (see
docs/Memory.md's "Device" section for the full design writeup). Mirrors
tests/test_phase25.py's style and rigor: every new correctness claim is
checked here explicitly against real simulation output, not just asserted
in prose.

Covers, per this task's explicit ask:
  - determinism (same seed -> byte-identical device assignment / CSV output)
  - the sharing-fraction's ACTUAL observed rate reconciled against
    DEVICE_HOUSEHOLD_SHARING_FRACTION
  - a device's owner is always a real Person, and a shared device's owners
    are always members of exactly one Household (never across households)

Run with:
    python -m pytest tests/ -v          (from inside Simulation/)
    python -m pytest tests/test_device.py -v
"""

from __future__ import annotations

import dataclasses
import datetime
import filecmp
import os
import tempfile

from run_simulation import run
from world.engine import DEVICE_HOUSEHOLD_SHARING_FRACTION, SimulationEngine

START_DATE = datetime.date(2026, 1, 1)


def _engine(seed: int = 7, **overrides) -> SimulationEngine:
    kwargs = dict(
        seed=seed,
        num_persons=300,
        num_banks=3,
        num_merchants=6,
        num_days=60,
        start_date=START_DATE,
    )
    kwargs.update(overrides)
    return SimulationEngine(**kwargs)


# ---------------------------------------------------------------------------
# Every person has exactly one device; a device's owner(s) are always real
# Persons, and a shared device never crosses a household boundary.
# ---------------------------------------------------------------------------


def test_every_person_has_exactly_one_device():
    result = _engine(seed=1).run()
    person_ids = {p.person_id for p in result.persons}

    seen: set[str] = set()
    for d in result.devices:
        for pid in d.owner_person_ids:
            assert pid not in seen, f"{pid} appears as an owner of more than one device"
            seen.add(pid)
    assert seen == person_ids, "every Person must be linked to exactly one Device, and vice versa"


def test_every_device_owner_is_a_real_person():
    result = _engine(seed=2).run()
    person_ids = {p.person_id for p in result.persons}
    for d in result.devices:
        assert d.owner_person_ids, f"{d.device_id} has no owners at all"
        for pid in d.owner_person_ids:
            assert pid in person_ids, f"{d.device_id} claims owner {pid!r}, not a real person_id"


def test_shared_device_owners_never_cross_a_household_boundary():
    """The one legitimate sharing mechanism is household-scoped by
    construction -- proven here on real output, not just claimed: every
    device with >=2 owners has ALL of its owners inside exactly one
    Household's person_ids, never split across two households."""
    result = _engine(seed=4).run()
    household_by_person = {pid: h.household_id for h in result.households for pid in h.person_ids}

    checked_shared = 0
    for d in result.devices:
        if len(d.owner_person_ids) < 2:
            continue
        household_ids = {household_by_person[pid] for pid in d.owner_person_ids}
        assert len(household_ids) == 1, (
            f"{d.device_id} is shared across households {household_ids} -- "
            f"sharing must be confined to one household"
        )
        checked_shared += 1
    assert checked_shared > 0, "expected at least one genuinely shared (>=2 owner) device in this run"


def test_no_device_shared_by_fewer_than_two_owners_is_mislabeled():
    """A device with exactly one owner is a personal device, not a 'shared'
    one -- sanity check that owner_person_ids never contains a duplicate
    (which would silently masquerade a personal device as multi-owner)."""
    result = _engine(seed=6).run()
    for d in result.devices:
        assert len(d.owner_person_ids) == len(set(d.owner_person_ids)), (
            f"{d.device_id} lists the same owner more than once: {d.owner_person_ids}"
        )


# ---------------------------------------------------------------------------
# Sharing-fraction accuracy: reconcile the ACTUAL observed sharing rate
# against DEVICE_HOUSEHOLD_SHARING_FRACTION.
# ---------------------------------------------------------------------------


def test_device_sharing_fraction_matches_the_stated_constant():
    """Every household with 2+ members contributes (size - 1) independent
    Bernoulli(DEVICE_HOUSEHOLD_SHARING_FRACTION) trials (one per non-primary
    member -- see world/engine.py's device-assignment pass). Reconciles the
    actual observed fraction of non-primary members who ended up sharing
    against the stated constant, over a large enough sample that sampling
    noise stays small -- same style as test_phase25.py's SAVINGS_SWEEP_
    FRACTION/HOUSEHOLD_SWEEP_FRACTION reconciliation tests, just with a
    statistical tolerance band instead of an exact match, since this one
    (unlike the sweep fractions, which are arithmetic splits of a fixed
    amount) is a genuine per-person coin flip."""
    result = _engine(seed=8, num_persons=2000, num_banks=4, num_merchants=10, num_days=30).run()

    household_by_person = {pid: h.household_id for h in result.households for pid in h.person_ids}
    device_by_person = {pid: d.device_id for d in result.devices for pid in d.owner_person_ids}

    eligible_trials = 0  # non-primary members of households with size >= 2
    shared_trials = 0  # of those, how many ended up on a device with >=2 owners
    for h in result.households:
        if len(h.person_ids) < 2:
            continue
        primary_id = h.person_ids[0]
        primary_device_id = device_by_person[primary_id]
        for pid in h.person_ids[1:]:
            eligible_trials += 1
            if device_by_person[pid] == primary_device_id:
                shared_trials += 1

    assert eligible_trials > 500, "expected a large enough sample of eligible household members"
    actual_fraction = shared_trials / eligible_trials
    # A generous statistical tolerance (not an exact-match assertion,
    # unlike the sweep-fraction tests) -- this is a real Bernoulli draw,
    # not an arithmetic split, so some sampling noise is expected even at
    # this sample size. 5 percentage points comfortably covers normal
    # binomial variance here (std dev ~= sqrt(0.3*0.7/eligible_trials),
    # well under 0.02 at eligible_trials > 500) while still catching a
    # genuinely broken/disconnected constant.
    assert abs(actual_fraction - DEVICE_HOUSEHOLD_SHARING_FRACTION) < 0.05, (
        f"actual device-sharing fraction {actual_fraction:.3f} != "
        f"DEVICE_HOUSEHOLD_SHARING_FRACTION {DEVICE_HOUSEHOLD_SHARING_FRACTION} "
        f"(outside +/-0.05 tolerance over {eligible_trials} trials)"
    )


# ---------------------------------------------------------------------------
# Determinism (Rules.md #6)
# ---------------------------------------------------------------------------


def test_same_seed_produces_identical_devices_in_memory():
    result_a = _engine(seed=123).run()
    result_b = _engine(seed=123).run()

    assert len(result_a.devices) == len(result_b.devices)
    assert [dataclasses.asdict(d) for d in result_a.devices] == [
        dataclasses.asdict(d) for d in result_b.devices
    ]


def test_same_seed_produces_byte_identical_devices_csv():
    with tempfile.TemporaryDirectory() as tmp:
        outdir_a = os.path.join(tmp, "run_a")
        outdir_b = os.path.join(tmp, "run_b")

        run(seed=55, population=150, banks=2, merchants=4, days=30, start_date=START_DATE, outdir=outdir_a)
        run(seed=55, population=150, banks=2, merchants=4, days=30, start_date=START_DATE, outdir=outdir_b)

        for filename in ("devices.csv", "transactions.csv"):
            path_a = os.path.join(outdir_a, filename)
            path_b = os.path.join(outdir_b, filename)
            assert os.path.exists(path_a)
            assert os.path.exists(path_b)
            assert filecmp.cmp(path_a, path_b, shallow=False), (
                f"{filename} differs between two runs with the same seed"
            )


def test_different_seeds_produce_different_device_assignment():
    result_a = _engine(seed=1).run()
    result_b = _engine(seed=2).run()

    devices_a = [dataclasses.asdict(d) for d in result_a.devices]
    devices_b = [dataclasses.asdict(d) for d in result_b.devices]
    assert devices_a != devices_b, "different seeds unexpectedly produced identical device assignment"
