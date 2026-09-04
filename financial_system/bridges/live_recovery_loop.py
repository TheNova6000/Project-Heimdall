"""
Live Recovery loop: closes Recovery's one-way bridge into a REAL, in-loop
retry loop. See `financial_system/bridges/README.md`'s "Live Recovery loop"
section for the full design write-up; this docstring covers the essential
contract only.

WHAT THIS IS (bounded, honestly, by design -- read before extending):
a genuinely SMALL Simulation/ world (few-people population, not the
300-person scale the batch bridge uses) is driven day-by-day. After EVERY
simulated day, the world's ENTIRE real transaction stream so far is
re-ingested through Heimdall's real Phase 1/2/3 pipeline (unmodified), and
EVERY new `payment_failure` that occurred -- not a sample, not a filtered
subset -- gets a real decision from Heimdall's real, unmodified
`recovery.recovery_agent.run_recovery_for_payment()`. If that decision is
RETRY, a real retry purchase is scheduled and later actually attempted
against the person's real, then-current balance, via the new
`SimulationEngine.attempt_retry()` method (Simulation/world/engine.py).

The "smallness" here is a SHRUNK CANVAS, not a filtered stream: at a small
population, the bank agent watches its whole small world's real activity
(salary, purchases, settlement, failures -- everything Simulation/ produces),
and every `payment_failure` in that stream gets evaluated. Nothing is
sampled or cherry-picked out of a larger population -- see README.md for
why this replaced an earlier sampling design during this task.

SCOPE: Recovery only. Risk and Controller reacting live to other
transaction types is explicitly out of scope for this task -- future work,
not attempted here (same honesty convention as every domain-scoping
decision already in this repository).

DETERMINISM (the property this whole design exists to protect -- see
Simulation/docs/Rules.md #6 and this module's own "Determinism" section in
README.md for the full argument): same seed + same config -> byte-identical
output, INCLUDING every retry transaction and every Heimdall decision. This
holds because:
  1. Heimdall's own decision logic is a pure function of graph state (no
     RNG, no LLM -- confirmed by reading recovery_agent.py/signals.py
     directly, see README.md).
  2. Every payment considered at a checkpoint is processed in a FIXED order
     (sorted by payment_id, which sorts identically to the underlying
     Simulation transaction_id -- a zero-padded monotonic hex counter, never
     dict/set iteration order).
  3. `attempt_retry()` calls happen in a FIXED position in the day loop
     (immediately before that day's own `run_one_tick()`, i.e. before any of
     that day's own core RNG draws), in a FIXED order (sorted by
     `original_transaction_id`) among retries scheduled for the same day.
  4. Nothing here calls Python's global `random` module or reads wall-clock
     time -- the only randomness anywhere in this loop is Simulation's own
     single seeded `engine.rng`, consumed by `attempt_retry()`'s
     `_event_timestamp()` call, in the fixed position above.
"""
from __future__ import annotations

import datetime
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SIMULATION_DIR = REPO_ROOT / "Simulation"
if str(SIMULATION_DIR) not in sys.path:
    sys.path.insert(0, str(SIMULATION_DIR))

import run_simulation  # Simulation/run_simulation.py -- reused as a library (write_output()), unmodified
from world.engine import SimulationEngine  # Simulation/'s real, unmodified engine (+ this task's additive methods)

from financial_system.bridges.simulation_bridge import transform_simulation_output
from financial_system.entity_resolution.given_matches import resolve_given_matches, validate_reference_keys
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_state.builder import build_financial_state
from financial_system.recovery.recovery_agent import run_recovery_for_payment

# `RETRY_ALT_METHOD`'s own real semantics (financial_system/recovery/signals.py's
# FAILURE_TAXONOMY, also mirrored in financial_system/data_generator/
# generate_dataset.py) mean "retry through a DIFFERENT payment method" --
# Simulation/ has no alternate-payment-method concept at all (every purchase
# uses whatever single account/device the person already has), so this
# action is deliberately NOT executed as a same-account retry (that would
# misrepresent what Heimdall's decision meant). It is logged, not silently
# dropped -- see `_process_new_failures` below. Never actually produced by
# Simulation-derived data today (the only failure_reason Simulation ever
# emits is `insufficient_funds` -> RETRY_LATER), kept here for correctness
# if that ever changes.
_NOT_EXECUTABLE_ACTIONS = {"RETRY_ALT_METHOD"}


@dataclass
class RetrySchedule:
    original_transaction_id: str
    person_id: str
    merchant_id: str
    amount: float
    target_day: int
    proposed_action: str
    failure_day: int


@dataclass
class DecisionRecord:
    payment_id: str
    original_transaction_id: str
    decision: str
    proposed_action: str
    decision_score: float
    reason: str
    day_evaluated: int
    # AgentVerdict.investigation_confidence -- "Discovery.AI's own, audit-only"
    # (financial_system/verdict.py). Only ever non-None when
    # investigate_evidence() actually ran, which requires investigate=True
    # AND an unrecognized failure_reason (recovery_agent.py's own logic).
    # This loop always calls run_recovery_for_payment(..., investigate=False)
    # (see below), so this is always None here -- kept on the record, not
    # just asserted, so a test can prove zero LLM calls directly from real
    # output rather than by trusting the call site.
    investigation_confidence: float | None = None


@dataclass
class RetryOutcome:
    original_transaction_id: str
    day_attempted: int
    succeeded: bool


@dataclass
class LiveLoopReport:
    seed: int
    population: int
    days: int
    checkpoints_run: int
    total_transactions_final: int
    failed_payments_total: int
    decisions: list = field(default_factory=list)          # list[DecisionRecord]
    retries_scheduled: list = field(default_factory=list)  # list[RetrySchedule]
    retries_not_executable: list = field(default_factory=list)  # list[RetrySchedule], RETRY_ALT_METHOD
    retries_attempted: list = field(default_factory=list)  # list[RetryOutcome]

    @property
    def decision_counts(self) -> dict:
        counts: dict[str, int] = {}
        for d in self.decisions:
            counts[d.decision] = counts.get(d.decision, 0) + 1
        return counts

    @property
    def retries_succeeded(self) -> int:
        return sum(1 for r in self.retries_attempted if r.succeeded)

    @property
    def retries_failed_again(self) -> int:
        return sum(1 for r in self.retries_attempted if not r.succeeded)

    @property
    def retries_never_reached(self) -> list:
        """Scheduled retries whose target_day fell on/after the run's last
        simulated day (day == self.days) -- same honest, expected boundary
        caveat as _run_settlement's own last-day proceeds (Simulation/docs/
        Memory.md, Phase 2 section): a run has to end somewhere, and a
        retry due exactly on the day the run stops has no later day left to
        actually attempt it on. Not a bug -- reported explicitly, not
        hidden."""
        attempted_ids = {r.original_transaction_id for r in self.retries_attempted}
        return [s for s in self.retries_scheduled if s.original_transaction_id not in attempted_ids]


def _txn_id_from_payment_id(payment_id: str) -> str:
    prefix = "pay_bridge_"
    assert payment_id.startswith(prefix), f"unexpected payment_id shape: {payment_id!r}"
    return payment_id[len(prefix):]


def run_live_recovery_loop(
    seed: int,
    population: int,
    banks: int,
    merchants: int,
    days: int,
    start_date: datetime.date,
    work_dir: Path,
) -> LiveLoopReport:
    """
    Drives a fresh SimulationEngine day-by-day. After EVERY simulated day,
    rebuilds Heimdall's real financial_state store + graph from the world's
    full transaction history so far (see module docstring -- this is
    tractable daily specifically because the canvas is small), and calls
    Heimdall's real `run_recovery_for_payment()` on every NEW
    `payment_failure` payment (never previously decided). Every RETRY
    decision whose `proposed_action` is executable in Simulation/'s own
    mechanics (RETRY_PAYMENT or RETRY_LATER -- both map onto "retry as soon
    as the next simulated day allows", the finest granularity Simulation/'s
    day-tick clock has; see README.md for why these two collapse to the
    same schedule today) gets a real `attempt_retry()` call on its target
    day, against the person's real balance AT THAT LATER POINT.
    """
    work_dir = Path(work_dir)
    sim_snapshot_dir = work_dir / "sim_snapshot"
    bridge_raw_dir = work_dir / "raw"
    state_db = work_dir / "financial_state.db"
    graph_db = work_dir / "financial_graph.db"
    work_dir.mkdir(parents=True, exist_ok=True)

    engine = SimulationEngine(
        seed=seed, num_persons=population, num_banks=banks,
        num_merchants=merchants, num_days=days, start_date=start_date,
    )

    decided_payment_ids: set[str] = set()
    # target_day -> list[RetrySchedule], each list kept in the fixed order
    # (sorted by original_transaction_id) it must be executed in.
    retry_schedule: dict[int, list[RetrySchedule]] = {}

    report = LiveLoopReport(
        seed=seed, population=population, days=days, checkpoints_run=0,
        total_transactions_final=0, failed_payments_total=0,
    )

    for day in range(days):
        # -- 1. Execute any retries scheduled for `day`, BEFORE that day's
        # own run_one_tick() -- a fixed position in the loop every run
        # (see module docstring, "Determinism"). engine.clock.day == day
        # here (clock has not yet been advanced for this iteration), so
        # attempt_retry()'s own _record() call lands on the correct day.
        due = sorted(retry_schedule.pop(day, []), key=lambda s: s.original_transaction_id)
        for sched in due:
            succeeded = engine.attempt_retry(
                original_transaction_id=sched.original_transaction_id,
                person_id=sched.person_id,
                merchant_id=sched.merchant_id,
                amount=sched.amount,
                day=day,
            )
            report.retries_attempted.append(
                RetryOutcome(original_transaction_id=sched.original_transaction_id,
                             day_attempted=day, succeeded=succeeded)
            )

        # -- 2. Run this simulated day, exactly as run() would.
        engine.run_one_tick()

        # -- 3. Checkpoint: re-ingest the world's full history so far through
        # Heimdall's real, unmodified Phase 1/2/3 pipeline, and evaluate
        # EVERY new payment_failure -- see module docstring for why this is
        # done every day (small canvas, cheap rebuild) rather than sampled
        # or batched at a coarser frequency.
        report.checkpoints_run += 1
        snapshot = engine.snapshot()
        run_simulation.write_output(snapshot, str(sim_snapshot_dir))
        transform_simulation_output(sim_snapshot_dir, bridge_raw_dir)
        store, _phase1_result = build_financial_state(db_path=state_db, raw_dir=bridge_raw_dir)
        validate_reference_keys(store)
        given = resolve_given_matches(store)
        store.clear_entity_matches()
        for m in given:
            store.add_entity_match(m.subject_type, m.subject_id, m.object_type, m.object_id,
                                    m.relation, m.match_method, m.match_score, m.match_evidence,
                                    m.source_record_ids)
        store.commit()
        graph_state, graph = build_graph(state_db=state_db, graph_db=graph_db)

        # Fixed order every run: sort by payment_id, which sorts identically
        # to the underlying Simulation transaction_id (zero-padded monotonic
        # hex counter) -- never store.all_rows()'s own row order.
        all_failed = sorted(
            r["payment_id"] for r in store.all_rows("payments") if r["status"] == "failed"
        )
        new_failures = [pid for pid in all_failed if pid not in decided_payment_ids]
        report.failed_payments_total = len(all_failed)

        if new_failures:
            # Truman's own transaction records are the source of truth for
            # "the original failed purchase's own amount/merchant" -- read
            # directly from the live engine, not re-derived from the
            # bridge's transformed CSV.
            txn_by_id = {t.transaction_id: t for t in engine.transactions}

            for pid in new_failures:
                decided_payment_ids.add(pid)
                verdict = run_recovery_for_payment(graph, pid, investigate=False)
                original_txn_id = _txn_id_from_payment_id(pid)
                report.decisions.append(DecisionRecord(
                    payment_id=pid, original_transaction_id=original_txn_id,
                    decision=verdict.decision, proposed_action=verdict.proposed_action,
                    decision_score=verdict.decision_score, reason=verdict.reason,
                    day_evaluated=day, investigation_confidence=verdict.investigation_confidence,
                ))

                if verdict.decision != "RETRY":
                    continue

                orig_txn = txn_by_id[original_txn_id]
                sched = RetrySchedule(
                    original_transaction_id=original_txn_id,
                    person_id=orig_txn.from_id, merchant_id=orig_txn.to_id,
                    amount=orig_txn.amount, target_day=day + 1,
                    proposed_action=verdict.proposed_action, failure_day=orig_txn.day,
                )
                if verdict.proposed_action in _NOT_EXECUTABLE_ACTIONS:
                    report.retries_not_executable.append(sched)
                    continue
                # RETRY_PAYMENT / RETRY_LATER both schedule for day + 1 --
                # the next day is the earliest this checkpoint-based loop
                # can act (checkpointing happens once per day, AFTER that
                # day's own run_one_tick()), and it is also exactly
                # NORTH_STAR.md Working Section 23's own "WAIT 24 HOURS"
                # example given Simulation/'s day-granular clock. See
                # README.md for the full justification of this collapse.
                report.retries_scheduled.append(sched)
                retry_schedule.setdefault(sched.target_day, []).append(sched)

        # Close every sqlite connection opened this checkpoint (build_graph
        # opens its OWN second FinancialStateStore connection on state_db,
        # in addition to the one build_financial_state already returned, and
        # the graph connection itself) before the next day's checkpoint
        # tries to unlink() and rebuild the same db paths -- required on
        # Windows, where unlink() fails on a file still held open by another
        # handle (POSIX allows it; this loop must work on both).
        store.close()
        graph_state.close()
        graph.close()

    report.total_transactions_final = len(engine.transactions)
    return report


def _default_work_dir() -> Path:
    return Path(__file__).resolve().parent / "live_bridge_output"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Live Recovery loop (Simulation/ <-> Heimdall, in-loop retries)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--population", type=int, default=20)
    parser.add_argument("--banks", type=int, default=2)
    parser.add_argument("--merchants", type=int, default=4)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--start-date", type=str, default="2026-01-01")
    parser.add_argument("--work-dir", type=str, default=str(_default_work_dir()))
    args = parser.parse_args()

    import time
    t0 = time.time()
    result = run_live_recovery_loop(
        seed=args.seed, population=args.population, banks=args.banks,
        merchants=args.merchants, days=args.days,
        start_date=datetime.date.fromisoformat(args.start_date),
        work_dir=Path(args.work_dir),
    )
    elapsed = time.time() - t0

    print(f"LIVE RECOVERY LOOP: seed={args.seed} population={args.population} "
          f"banks={args.banks} merchants={args.merchants} days={args.days}")
    print(f"  wall-clock time: {elapsed:.2f}s ({result.checkpoints_run} daily checkpoints)")
    print(f"  total transactions (final): {result.total_transactions_final}")
    print(f"  failed payments (total, cumulative): {result.failed_payments_total}")
    print(f"  Recovery decisions made: {len(result.decisions)}  {result.decision_counts}")
    print(f"  retries scheduled (executable): {len(result.retries_scheduled)}")
    print(f"  retries not executable (RETRY_ALT_METHOD, no Simulation/ mechanic): {len(result.retries_not_executable)}")
    print(f"  retries actually attempted: {len(result.retries_attempted)}")
    print(f"    succeeded: {result.retries_succeeded}")
    print(f"    failed again: {result.retries_failed_again}")
    print(f"  retries scheduled but never reached (target day >= run end): {len(result.retries_never_reached)}")
