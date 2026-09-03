"""
Adversarial tests for TEMPORAL_MODEL_SPEC.md, run against the real Stage
1-4 code -- not a thought experiment where the capability already exists.
Scenarios the current implementation genuinely cannot exercise yet
(as_of, reversal-after-settlement) are reported as gaps, not faked.

Run directly: `python -m financial_system.events.adversarial_test`
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from financial_system.action.action_store import ActionStore
from financial_system.action.event_execution import execute_action_with_events
from financial_system.events.models import Event
from financial_system.events.store import (
    CausationOrderViolation, DuplicateEvent, EventStore, TemporalOrderViolation,
)
from financial_system.financial_graph.builder import build_graph
from financial_system.policy.engine import evaluate
from financial_system.recovery.recovery_agent import run_recovery_for_payment

NOW = datetime.now(timezone.utc)


def test_duplicate_event() -> bool:
    print("-- 1. Duplicate event --")
    store = EventStore(":memory:")
    e = Event(event_id="e1", event_type="PaymentCreated", subject_id="pay_x", source="test",
              source_event_id="row_1", occurred_at=NOW, recorded_at=NOW, correlation_id="pay_x")
    store.append(e)
    try:
        store.append(Event(event_id="e2", event_type="PaymentCreated", subject_id="pay_x", source="test",
                            source_event_id="row_1", occurred_at=NOW, recorded_at=NOW, correlation_id="pay_x"))
        ok = False
    except DuplicateEvent:
        ok = True
    print(f"  second append with same (source, source_event_id) rejected: {ok}")
    print("PASS" if ok else "FAIL")
    return ok


def test_out_of_order_causation() -> bool:
    print("\n-- 2. Out-of-order event (causation pointing to the future) --")
    store = EventStore(":memory:")
    later = Event(event_id="later", event_type="PaymentFailed", subject_id="pay_x", source="test",
                   occurred_at=NOW, recorded_at=NOW, correlation_id="pay_x")
    store.append(later)
    try:
        store.append(Event(event_id="earlier", event_type="PaymentCreated", subject_id="pay_x", source="test",
                            occurred_at=NOW - timedelta(hours=1), recorded_at=NOW, correlation_id="pay_x",
                            causation_id="later"))  # claims to be CAUSED BY a later event
        ok = False
    except CausationOrderViolation:
        ok = True
    print(f"  event caused by a chronologically later event rejected: {ok}")
    print("PASS" if ok else "FAIL")
    return ok


def test_late_event() -> bool:
    print("\n-- 3. Late event (occurred long before recorded) --")
    store = EventStore(":memory:")
    occurred = NOW - timedelta(days=3)
    recorded = NOW
    e = Event(event_id="late1", event_type="BankTransactionRecorded", subject_id="btx_x", source="test",
              occurred_at=occurred, recorded_at=recorded, correlation_id="btx_x")
    accepted = True
    try:
        store.append(e)
    except Exception:
        accepted = False
    fetched = store.get("late1")
    gap_preserved = fetched is not None and (fetched.recorded_at - fetched.occurred_at) >= timedelta(days=2)
    ok = accepted and gap_preserved
    print(f"  accepted despite a 3-day occurred/recorded gap: {accepted}")
    print(f"  gap preserved on read-back: {gap_preserved}")
    print("PASS" if ok else "FAIL")
    return ok


def test_recorded_before_occurred_gap() -> bool:
    """Spec §Event invariants #7: recorded_at >= occurred_at, now enforced
    at EventStore.append(). Was informational (confirmed the gap existed);
    now a real gate confirming the gap is closed."""
    print("\n-- 6. recorded_at < occurred_at is rejected at the write boundary --")
    store = EventStore(":memory:")
    e = Event(event_id="impossible1", event_type="PaymentCreated", subject_id="pay_y", source="test",
              occurred_at=NOW, recorded_at=NOW - timedelta(hours=1), correlation_id="pay_y")
    rejected = False
    try:
        store.append(e)
    except TemporalOrderViolation:
        rejected = True
    ok = rejected and store.count() == 0
    print(f"  store rejected an event recorded BEFORE it occurred: {rejected}")
    print(f"  event count after rejection: {store.count()} (expected 0 -- rejected events never enter history)")
    print("PASS" if ok else "FAIL")
    return ok


def test_naive_and_aware_normalize_consistently() -> bool:
    """occurred_at/recorded_at are normalized to aware UTC at the write
    boundary regardless of what a caller passes in -- naive (as backfilled
    CSV timestamps are) and aware (as live events are) must compare
    correctly against each other and against as_of once stored."""
    print("\n-- 7. naive and aware timestamps normalize to the same stored value --")
    store = EventStore(":memory:")
    naive_t = datetime(2026, 1, 1, 12, 0, 0)
    aware_t = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    store.append(Event(event_id="naive1", event_type="PaymentCreated", subject_id="pay_naive",
                        source="test", occurred_at=naive_t, recorded_at=naive_t, correlation_id="pay_naive"))
    store.append(Event(event_id="aware1", event_type="PaymentCreated", subject_id="pay_aware",
                        source="test", occurred_at=aware_t, recorded_at=aware_t, correlation_id="pay_aware"))
    naive_stored = store.get("naive1")
    aware_stored = store.get("aware1")
    both_aware = naive_stored.occurred_at.tzinfo is not None and aware_stored.occurred_at.tzinfo is not None
    equal_instant = naive_stored.occurred_at == aware_stored.occurred_at
    # as_of exactly at that instant must see both -- proves the normalization
    # a store-internal reader (as_of filtering) relies on actually holds.
    visible = {e.subject_id for e in store.all_events(as_of=aware_t)}
    ok = both_aware and equal_instant and visible == {"pay_naive", "pay_aware"}
    print(f"  both stored occurred_at are timezone-aware: {both_aware}")
    print(f"  naive-input and aware-input resolve to the same instant: {equal_instant}")
    print(f"  as_of at that instant sees both: {visible == {'pay_naive', 'pay_aware'}}")
    print("PASS" if ok else "FAIL")
    return ok


def test_two_genuine_retries(graph) -> bool:
    print("\n-- 4. Two genuine retry attempts (not one retry + one escalation) --")
    events, actions = EventStore(":memory:"), ActionStore(":memory:")

    import csv
    from pathlib import Path
    gt = Path(__file__).resolve().parent.parent.parent / "financial_system" / "data" / "ground_truth" / "recovery_labels.csv"
    with open(gt, newline="", encoding="utf-8") as f:
        row = next(r for r in csv.DictReader(f) if r["failure_reason"] == "technical_failure")
    pid = row["payment_id"]

    verdict = run_recovery_for_payment(graph, pid, investigate=False)
    policy = evaluate(verdict, has_conflict=False)

    # attempt_number 2/3: this payment's own PaymentFailed (backfilled) is
    # already overall attempt 1 -- these two direct retries are 2 and 3.
    key1 = f"{pid}:attempt2:{policy.proposed_action}"
    key2 = f"{pid}:attempt3:{policy.proposed_action}"  # same action_type, different attempt
    r1 = execute_action_with_events(verdict, policy, key1, pid, events, actions, attempt_number=2)
    r2 = execute_action_with_events(verdict, policy, key2, pid, events, actions, attempt_number=3)

    distinct_actions = actions.get_by_idempotency_key(key1).action_id != actions.get_by_idempotency_key(key2).action_id
    outcome_events = events.all_events("ActionOutcomeObserved")
    ok = distinct_actions and len(outcome_events) == 2
    print(f"  attempt1 key={key1!r} action_id={actions.get_by_idempotency_key(key1).action_id[:8]}")
    print(f"  attempt2 key={key2!r} action_id={actions.get_by_idempotency_key(key2).action_id[:8]}")
    print(f"  distinct Action rows: {distinct_actions}, ActionOutcomeObserved count: {len(outcome_events)} (expected 2)")
    print("PASS" if ok else "FAIL")
    return ok


def test_projection_replay_idempotent() -> bool:
    print("\n-- 5. Same event log replayed twice -> identical projection --")
    # Re-confirms Stage 1 Gate 1's own property directly, as a named
    # adversarial case rather than assuming it still holds.
    from financial_system.events.backfill import backfill
    from financial_system.events.projection import project
    from financial_system.financial_state.store import FinancialStateStore
    from financial_system.ingestion import reference_ingestion
    from pathlib import Path
    import tempfile

    raw_dir = Path(__file__).resolve().parent.parent.parent / "financial_system" / "data" / "raw"
    with tempfile.TemporaryDirectory() as tmp:
        events_db = Path(tmp) / "ev.db"
        events = EventStore(events_db)
        backfill(events, raw_dir)

        results = []
        for i in (1, 2):
            state_db = Path(tmp) / f"state_{i}.db"
            state = FinancialStateStore(state_db)
            run_id = f"replay_{i}"
            for fn in (reference_ingestion.ingest_merchants, reference_ingestion.ingest_customers,
                       reference_ingestion.ingest_devices, reference_ingestion.ingest_instruments):
                fn(state, raw_dir, run_id)
            state.commit()
            project(events, state)
            results.append(state.sum_decimal("payments", "amount"))
            state.close()  # Windows holds a file lock on an open sqlite3 connection --
                            # must close before TemporaryDirectory's own cleanup runs.
        events.close()

        ok = results[0] == results[1]
        print(f"  payments.amount sum, replay 1: {results[0]}, replay 2: {results[1]}")
        print("PASS" if ok else "FAIL")
        return ok


def test_rejected_event_invisible_to_projection() -> bool:
    """An invalid event cannot enter history, therefore it cannot enter
    state: append() rejecting it must mean projection never sees it --
    checked directly against the real backfilled log, not asserted."""
    print("\n-- 8. A rejected event never becomes visible through projection --")
    from financial_system.events.backfill import backfill
    from financial_system.events.projection import project
    from financial_system.financial_state.store import FinancialStateStore
    from financial_system.ingestion import reference_ingestion
    from pathlib import Path
    import tempfile

    raw_dir = Path(__file__).resolve().parent.parent.parent / "financial_system" / "data" / "raw"
    with tempfile.TemporaryDirectory() as tmp:
        events_db = Path(tmp) / "ev.db"
        events = EventStore(events_db)
        backfill(events, raw_dir)
        count_before = events.count()

        state_db = Path(tmp) / "state.db"
        state = FinancialStateStore(state_db)
        for fn in (reference_ingestion.ingest_merchants, reference_ingestion.ingest_customers,
                   reference_ingestion.ingest_devices, reference_ingestion.ingest_instruments):
            fn(state, raw_dir, "before_reject")
        state.commit()
        project(events, state)
        sum_before = state.sum_decimal("payments", "amount")
        state.close()

        rejected = False
        try:
            events.append(Event(
                event_id="poison", event_type="PaymentCreated", subject_id="pay_poison", source="test",
                occurred_at=NOW, recorded_at=NOW - timedelta(hours=1), correlation_id="pay_poison",
                payload={"payment_id": "pay_poison", "order_id": "ord_poison", "customer_id": "cust_poison",
                         "merchant_id": "merch_poison", "device_id": "dev_poison", "instrument_id": "instr_poison",
                         "amount": "999999.99", "currency": "INR", "created_at": NOW.isoformat(), "attempt_number": 1},
            ))
        except TemporalOrderViolation:
            rejected = True
        count_after = events.count()

        state_db2 = Path(tmp) / "state2.db"
        state2 = FinancialStateStore(state_db2)
        for fn in (reference_ingestion.ingest_merchants, reference_ingestion.ingest_customers,
                   reference_ingestion.ingest_devices, reference_ingestion.ingest_instruments):
            fn(state2, raw_dir, "after_reject")
        state2.commit()
        project(events, state2)
        sum_after = state2.sum_decimal("payments", "amount")
        poison_visible = any(dict(r)["payment_id"] == "pay_poison" for r in state2.all_rows("payments"))
        state2.close()
        events.close()

        ok = rejected and count_after == count_before and sum_after == sum_before and not poison_visible
        print(f"  poison event rejected: {rejected}")
        print(f"  event count: {count_before} before -> {count_after} after (expected unchanged)")
        print(f"  projected payments.amount sum: {sum_before} before -> {sum_after} after (expected unchanged)")
        print(f"  poison payment visible in projection: {poison_visible} (expected False)")
        print("PASS" if ok else "FAIL")
        return ok


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("Building graph for retry-scoped tests...")
    _, graph = build_graph()

    results = {
        "duplicate_event": test_duplicate_event(),
        "out_of_order_causation": test_out_of_order_causation(),
        "late_event": test_late_event(),
        "two_genuine_retries": test_two_genuine_retries(graph),
        "projection_replay_idempotent": test_projection_replay_idempotent(),
        "recorded_before_occurred_rejected": test_recorded_before_occurred_gap(),
        "naive_and_aware_normalize_consistently": test_naive_and_aware_normalize_consistently(),
        "rejected_event_invisible_to_projection": test_rejected_event_invisible_to_projection(),
    }

    print("\n== summary ==")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")

    passed = all(results.values())
    print(f"\nADVERSARIAL TESTS: {'PASS' if passed else 'FAIL'}")
    sys.exit(0 if passed else 1)
