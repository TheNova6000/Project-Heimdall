"""
TEMPORAL_ADVERSARIAL_REVIEW.md's newly-added gates -- scenarios not already
covered by adversarial_test.py's 8 gates, asof_runner.py's 4, or
attempt_runner.py's 3. Every gate here is executed against the real
EventStore/projection/loop/Recovery code, never mocked. Where a scenario
turns out not to be organically reachable through the real pipeline (the
gateway simulator is deterministic per payment_id -- see simulator.py), that
limit is demonstrated and reported, not routed around.

Run directly: `python -m financial_system.events.temporal_adversarial_runner`
"""
from __future__ import annotations

import csv
import sys
import uuid
from datetime import timedelta
from pathlib import Path

from financial_system.action.action_store import ActionStore
from financial_system.action.loop import run_action_loop_v2
from financial_system.entity_resolution.runner import run_phase2
from financial_system.events.action_projection import project_action_outcome
from financial_system.events.backfill import backfill
from financial_system.events.models import Event
from financial_system.events.projection import project
from financial_system.events.store import DuplicateEvent, EventStore
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.builder import build_financial_state
from financial_system.financial_state.store import FinancialStateStore
from financial_system.ingestion import reference_ingestion
from financial_system.recovery.recovery_agent import run_recovery_for_payment

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "recovery_labels.csv"
RAW_DIR = REPO_ROOT / "financial_system" / "data" / "raw"
DATA_DIR = REPO_ROOT / "financial_system" / "data"

STATE_DB = DATA_DIR / "financial_state_tar.db"
GRAPH_DB = DATA_DIR / "financial_graph_tar.db"
GRAPH_DB_2 = DATA_DIR / "financial_graph_tar_2.db"
EVENTS_DB = DATA_DIR / "events_tar.db"
ACTIONS_DB = DATA_DIR / "actions_tar.db"


def _fresh(path: Path) -> None:
    if path.exists():
        path.unlink()


def setup():
    for p in (STATE_DB, GRAPH_DB, GRAPH_DB_2, EVENTS_DB, ACTIONS_DB):
        _fresh(p)
    events = EventStore(EVENTS_DB)
    backfill(events, RAW_DIR)
    state, _ = build_financial_state(db_path=STATE_DB, raw_dir=RAW_DIR)
    violations = run_phase2(db_path=STATE_DB)[0]
    assert not violations
    _, graph = build_graph(state_db=STATE_DB, graph_db=GRAPH_DB)
    actions = ActionStore(ACTIONS_DB)
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        row = next(r for r in csv.DictReader(f)
                   if r["failure_reason"] == "technical_failure" and r["retry_would_succeed"] == "True")
    return events, actions, graph, row["payment_id"]


# -- A: event history --

def test_event_id_collision() -> bool:
    print("-- A1. Same event_id, different payload -- distinct from the (source, source_event_id) dedup key --")
    store = EventStore(":memory:")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    store.append(Event(event_id="fixed-id", event_type="PaymentCreated", subject_id="pay_a", source="s1",
                        occurred_at=now, recorded_at=now, correlation_id="pay_a", payload={"v": 1}))
    rejected = False
    try:
        store.append(Event(event_id="fixed-id", event_type="PaymentFailed", subject_id="pay_b", source="s2",
                            occurred_at=now, recorded_at=now, correlation_id="pay_b", payload={"v": 2}))
    except DuplicateEvent:
        rejected = True
    stored = store.get("fixed-id")
    ok = rejected and stored.payload == {"v": 1} and stored.subject_id == "pay_a"
    print(f"  second append (same event_id, different type/subject/payload) rejected: {rejected}")
    print(f"  original event untouched: subject_id={stored.subject_id!r} payload={stored.payload}")
    print("PASS" if ok else "FAIL")
    return ok


def test_eventstore_restart_persistence() -> bool:
    print("\n-- A2. EventStore itself survives a simulated restart (new connection, same file) --")
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "restart.db"
        store1 = EventStore(db_path)
        backfill(store1, RAW_DIR)
        count1 = store1.count()
        store1.commit()
        store1.close()

        store2 = EventStore(db_path)  # fresh connection, nothing carried over in memory
        count2 = store2.count()
        sample = store2.events_for_subject(
            next(e.subject_id for e in store2.all_events("PaymentCreated")), "PaymentCreated")
        store2.close()

        ok = count1 == count2 and len(sample) == 1
        print(f"  event count before close: {count1}, after reopen: {count2}")
        print("PASS" if ok else "FAIL")
        return ok


# -- B: attempt history --

def test_three_attempt_sequence_at_projection_layer() -> bool:
    """The real gateway simulator (action/simulator.py::simulate_gateway_response)
    is deterministic per payment_id -- one fixed retry_would_succeed boolean,
    identical on every call. A genuine FAIL,FAIL,SUCCESS sequence for ONE
    payment therefore cannot be produced through the real loop+simulator as
    they exist today; this is a real, structural limit, stated here rather
    than routed around. What CAN be tested for real: whether projection.py's
    own merge logic correctly derives "latest attempt wins" for 3 attempts,
    by appending the events directly -- this exercises the actual
    projection code, just not through the simulator."""
    print("\n-- B1. Three-attempt sequence (FAIL, FAIL, SUCCESS) -- projection layer only --")
    print("  (simulator.py's verify_retry() is deterministic per payment_id -- cannot organically")
    print("   produce a differing outcome across attempts on ONE payment; see write-up)")
    import tempfile
    from datetime import datetime, timezone
    with tempfile.TemporaryDirectory() as tmp:
        events = EventStore(Path(tmp) / "ev.db")
        state = FinancialStateStore(Path(tmp) / "state.db")
        for fn in (reference_ingestion.ingest_merchants, reference_ingestion.ingest_customers,
                   reference_ingestion.ingest_devices, reference_ingestion.ingest_instruments):
            fn(state, RAW_DIR, "b1")
        state.commit()

        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        pid = "pay_synthetic_b1"
        events.append(Event(event_id=str(uuid.uuid4()), event_type="PaymentCreated", subject_id=pid,
                             source="test", occurred_at=t0, recorded_at=t0, correlation_id=pid,
                             payload={"payment_id": pid, "order_id": "ord_b1", "customer_id": "cust_0001",
                                      "merchant_id": "merch_001", "device_id": "dev_0001",
                                      "instrument_id": "instr_b1", "amount": "100.00", "currency": "INR",
                                      "created_at": t0.isoformat(), "attempt_number": 1}))
        events.append(Event(event_id=str(uuid.uuid4()), event_type="PaymentFailed", subject_id=pid,
                             source="test", occurred_at=t0, recorded_at=t0, correlation_id=pid,
                             payload={"status": "failed", "failure_reason": "technical_failure",
                                      "authorized_at": "", "captured_at": "", "attempt_number": 1}))
        for n, (delta, result) in enumerate([(1, "FAILURE"), (2, "FAILURE"), (3, "SUCCESS")], start=2):
            t = t0 + timedelta(hours=delta)
            events.append(Event(event_id=str(uuid.uuid4()), event_type="ActionOutcomeObserved", subject_id=pid,
                                 source="test", occurred_at=t, recorded_at=t, correlation_id=pid,
                                 payload={"action_id": f"a{n}", "executed": True, "action_taken": "RETRY_PAYMENT",
                                          "verification_result": result, "verification_detail": "",
                                          "attempt_number": n}))

        project(events, state)
        row = next(dict(r) for r in state.all_rows("payments") if dict(r)["payment_id"] == pid)
        outcomes = events.events_for_subject(pid, "ActionOutcomeObserved")
        attempt_seq = [(o.payload["attempt_number"], o.payload["verification_result"]) for o in outcomes]
        state.close()
        events.close()

        ok = (attempt_seq == [(2, "FAILURE"), (3, "FAILURE"), (4, "SUCCESS")]
              and row["status"] == "success" and row["failure_reason"] is None)
        print(f"  attempt sequence recorded: {attempt_seq}")
        print(f"  projected status: {row['status']!r}, failure_reason: {row['failure_reason']!r}")
        print("PASS" if ok else "FAIL")
        return ok


def test_retry_after_already_succeeded(events, actions, graph, pid) -> bool:
    print("\n-- B2. attempt 1 SUCCESS -> a further retry is requested -- does the system act? --")
    run_action_loop_v2(graph, pid, events, actions, investigate=False)
    events.commit()
    state = FinancialStateStore(STATE_DB)
    for e in events.events_for_subject(pid, "ActionOutcomeObserved"):
        project_action_outcome(e, state)
    _, graph2 = build_graph(state_db=STATE_DB, graph_db=GRAPH_DB_2)

    outcomes_before = len(events.events_for_subject(pid, "ActionOutcomeObserved"))
    case2 = run_action_loop_v2(graph2, pid, events, actions, investigate=False)
    events.commit()
    outcomes_after = events.events_for_subject(pid, "ActionOutcomeObserved")

    new_outcome = outcomes_after[-1]
    no_real_retry = (new_outcome.payload["action_taken"] == "NONE"
                      and new_outcome.payload["verification_result"] is None)
    ok = len(outcomes_after) == outcomes_before + 1 and no_real_retry and case2.case_status == "ALLOW"
    print(f"  second run_action_loop_v2() call on the now-succeeded payment: case_status={case2.case_status}")
    print(f"  new ActionOutcomeObserved payload: action_taken={new_outcome.payload['action_taken']!r} "
          f"verification_result={new_outcome.payload['verification_result']!r}")
    print(f"  no real gateway retry attempted (verification_result stays None): {no_real_retry}")
    print("  (structurally NOT blocked from being called -- but Recovery's status check + Policy's "
          "R10_RECOVERY_DO_NOT_RETRY_ALLOW rule reduce it to a safe no-op: an Action row and an "
          "ActionOutcomeObserved event ARE recorded, action_taken=NONE, verify_retry() never runs)")
    print("PASS" if ok else "FAIL")
    return ok


# -- C: projection determinism --

def test_cross_connection_determinism(events_path: Path, as_of) -> bool:
    print("\n-- C1. project(E, T) == project(E, T) across independent connections --")
    results = []
    for i in (1, 2):
        ev = EventStore(events_path)  # independent connection to the SAME file
        state_path = DATA_DIR / f"state_tar_det_{i}.db"
        _fresh(state_path)
        state = FinancialStateStore(state_path)
        for fn in (reference_ingestion.ingest_merchants, reference_ingestion.ingest_customers,
                   reference_ingestion.ingest_devices, reference_ingestion.ingest_instruments):
            fn(state, RAW_DIR, f"det_{i}")
        state.commit()
        project(ev, state, as_of=as_of)
        rows = sorted((dict(r)["payment_id"], dict(r)["status"], dict(r)["failure_reason"])
                      for r in state.all_rows("payments"))
        results.append(rows)
        state.close()
        ev.close()

    ok = results[0] == results[1]
    print(f"  {len(results[0])} payment rows compared across two independent connections/stores")
    print(f"  identical: {ok}")
    print("PASS" if ok else "FAIL")
    return ok


def test_late_event_retroactively_changes_as_of(events_path: Path, pid: str) -> bool:
    """A legitimate late-arriving event (occurred_at in the past, recorded_at
    now) changes what as_of=T means for a T at or after its occurred_at,
    even though T itself never changes -- this is correct event-sourcing
    behavior (late data), not a bug, and worth proving explicitly: as_of is
    not a fixed fact until every event with occurred_at <= T has actually
    been recorded."""
    print("\n-- G. A late-arriving event retroactively changes as_of=T (T fixed, new information arrives) --")
    from datetime import datetime, timezone
    ev = EventStore(events_path)
    t = datetime.now(timezone.utc) - timedelta(days=1)  # a T comfortably in the past

    def snapshot(run_id):
        path = DATA_DIR / f"state_tar_late_{run_id}.db"
        _fresh(path)
        state = FinancialStateStore(path)
        for fn in (reference_ingestion.ingest_merchants, reference_ingestion.ingest_customers,
                   reference_ingestion.ingest_devices, reference_ingestion.ingest_instruments):
            fn(state, RAW_DIR, run_id)
        state.commit()
        project(ev, state, as_of=t)
        row = next((dict(r) for r in state.all_rows("refunds") if dict(r)["payment_id"] == pid), None)
        state.close()
        return row

    before = snapshot("late_before")
    late_occurred = t - timedelta(hours=1)  # occurred before T
    late_recorded = datetime.now(timezone.utc)  # recorded now -- long after occurred, still valid (recorded>=occurred)
    ev.append(Event(event_id=str(uuid.uuid4()), event_type="RefundRecorded", subject_id="refund_synthetic_late",
                     source="test", occurred_at=late_occurred, recorded_at=late_recorded, correlation_id=pid,
                     payload={"refund_id": "refund_synthetic_late", "payment_id": pid, "amount": "1.00",
                              "reason": "late-arriving adjustment", "created_at": late_occurred.isoformat()}))
    ev.commit()
    after = snapshot("late_after")
    ev.close()

    ok = before is None and after is not None and after["refund_id"] == "refund_synthetic_late"
    print(f"  as_of={t.isoformat()}, BEFORE the late event was recorded: refund visible = {before is not None}")
    print(f"  as_of={t.isoformat()} (SAME T), AFTER the late event was recorded: refund visible = {after is not None}")
    print("  (T never changed -- what changed is which events have been recorded with occurred_at <= T)")
    print("PASS" if ok else "FAIL")
    return ok


def run() -> bool:
    print("Building event log (backfill + one live retry success)...")
    events, actions, graph, pid = setup()
    events_path = EVENTS_DB

    results = {
        "event_id_collision": test_event_id_collision(),
        "eventstore_restart_persistence": test_eventstore_restart_persistence(),
        "three_attempt_sequence_projection_layer": test_three_attempt_sequence_at_projection_layer(),
        "retry_after_already_succeeded": test_retry_after_already_succeeded(events, actions, graph, pid),
    }
    events.close()  # release the file before opening independent connections below

    from datetime import datetime, timezone
    results["cross_connection_determinism"] = test_cross_connection_determinism(
        events_path, datetime.now(timezone.utc))
    results["late_event_retroactive_as_of"] = test_late_event_retroactively_changes_as_of(events_path, pid)

    print("\n== summary ==")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    passed = all(results.values())
    print(f"\nTEMPORAL ADVERSARIAL RUNNER: {'PASS' if passed else 'FAIL'}")
    return passed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(0 if run() else 1)
