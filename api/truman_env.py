"""
A single, server-held, real Truman environment: one SimulationEngine
instance, advanced one real simulated day at a time on demand (not run to
completion in one blocking call), with Heimdall's real Recovery AND Risk
live loops both applied after every tick. This module does not reimplement
their logic -- the per-day body below inlines the same calls
financial_system/bridges/live_recovery_loop.py and live_risk_loop.py
already prove correct and deterministic (checkpoint -> rebuild the real
graph -> evaluate every new failure/eligible device -> real
retry/block), just driven interactively instead of in one batch call.

Ephemeral by design: this environment lives in server process memory only.
It is created once, lazily, on first use, and lost on server restart --
exactly like any other in-memory demo-scale environment, never claimed as
durable storage.
"""
from __future__ import annotations

import datetime
import json
import sys
import tempfile
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SIMULATION_DIR = REPO_ROOT / "Simulation"
if str(SIMULATION_DIR) not in sys.path:
    sys.path.insert(0, str(SIMULATION_DIR))

import run_simulation  # Simulation/run_simulation.py, reused as a library (write_output())
from world.engine import SimulationEngine  # Simulation/'s real, unmodified engine

from financial_system.bridges.simulation_bridge import transform_simulation_output
from financial_system.entity_resolution.given_matches import resolve_given_matches, validate_reference_keys
from financial_system.financial_graph.builder import build_graph
from financial_system.financial_graph.repository import GraphRepository
from financial_system.financial_state.builder import build_financial_state
from financial_system.recovery.recovery_agent import run_recovery_for_payment
from financial_system.risk.risk_agent import run_risk_for_device
from financial_system.risk.runner import devices_with_sharers

_BLOCKING_DECISIONS = {"REVIEW", "HOLD"}
_NOT_EXECUTABLE_ACTIONS = {"RETRY_ALT_METHOD"}  # RETRY_ALT_METHOD has no Simulation/ mechanic -- logged, not executed

SEED = 42
POPULATION = 20
BANKS = 2
MERCHANTS = 4
MAX_DAYS = 60
START_DATE = datetime.date(2026, 1, 1)


class TrumanEnvironment:
    def __init__(self):
        self.lock = threading.Lock()
        self.work_dir = Path(tempfile.mkdtemp(prefix="truman_env_"))
        self.sim_snapshot_dir = self.work_dir / "sim_snapshot"
        self.bridge_raw_dir = self.work_dir / "raw"
        self.state_db = self.work_dir / "financial_state.db"
        self.graph_db = self.work_dir / "financial_graph.db"

        self.engine = SimulationEngine(
            seed=SEED, num_persons=POPULATION, num_banks=BANKS,
            num_merchants=MERCHANTS, num_days=MAX_DAYS, start_date=START_DATE,
        )
        self.day = 0
        self.decided_payment_ids: set[str] = set()
        self.retry_schedule: dict[int, list[dict]] = {}
        self.blocked_devices: set[str] = set()
        self.log: list[dict] = []  # one real entry per tick already run
        self._rebuild_graph()  # a fresh environment already has a queryable day-0 graph

    def _rebuild_graph(self):
        run_simulation.write_output(self.engine.snapshot(), str(self.sim_snapshot_dir))
        transform_simulation_output(self.sim_snapshot_dir, self.bridge_raw_dir)
        store, _phase1_result = build_financial_state(db_path=self.state_db, raw_dir=self.bridge_raw_dir)
        validate_reference_keys(store)
        given = resolve_given_matches(store)
        store.clear_entity_matches()
        for m in given:
            store.add_entity_match(m.subject_type, m.subject_id, m.object_type, m.object_id,
                                    m.relation, m.match_method, m.match_score, m.match_evidence,
                                    m.source_record_ids)
        store.commit()
        graph_state, graph = build_graph(state_db=self.state_db, graph_db=self.graph_db)
        store.close()
        graph_state.close()
        graph.close()  # closed here; API handlers open their own short-lived read connection

    def graph(self) -> GraphRepository:
        return GraphRepository(self.graph_db)

    def tick(self) -> dict:
        with self.lock:
            if self.day >= MAX_DAYS:
                return {"day": self.day, "ended": True,
                        "message": f"This environment's {MAX_DAYS}-day horizon is complete."}

            day = self.day

            # -- Recovery: execute retries scheduled for `day`, BEFORE this
            # day's own tick (fixed position, same as live_recovery_loop.py).
            due = sorted(self.retry_schedule.pop(day, []), key=lambda s: s["original_transaction_id"])
            retries_attempted = []
            for sched in due:
                succeeded = self.engine.attempt_retry(
                    original_transaction_id=sched["original_transaction_id"],
                    person_id=sched["person_id"], merchant_id=sched["merchant_id"],
                    amount=sched["amount"], day=day,
                )
                retries_attempted.append({**sched, "succeeded": succeeded})

            self.engine.run_one_tick()
            self._rebuild_graph()

            recovery_decisions: list[dict] = []
            risk_decisions: list[dict] = []
            new_failures: list[str] = []
            devices_blocked_today: list[str] = []

            g = self.graph()
            try:
                rows = g._conn.execute(
                    "SELECT node_id, properties FROM graph_nodes WHERE node_type='Payment'"
                ).fetchall()
                all_failed = sorted(
                    row["node_id"] for row in rows
                    if json.loads(row["properties"]).get("status") == "failed"
                )
                new_failures = [pid for pid in all_failed if pid not in self.decided_payment_ids]

                txn_by_id = {t.transaction_id: t for t in self.engine.transactions}
                for pid in new_failures:
                    self.decided_payment_ids.add(pid)
                    verdict = run_recovery_for_payment(g, pid, investigate=False)
                    recovery_decisions.append({
                        "payment_id": pid, "decision": verdict.decision,
                        "proposed_action": verdict.proposed_action,
                        "decision_score": verdict.decision_score, "reason": verdict.reason,
                    })
                    if verdict.decision != "RETRY":
                        continue
                    orig_txn_id = pid[len("pay_bridge_"):]
                    orig_txn = txn_by_id.get(orig_txn_id)
                    if orig_txn is not None and verdict.proposed_action not in _NOT_EXECUTABLE_ACTIONS:
                        self.retry_schedule.setdefault(day + 1, []).append({
                            "original_transaction_id": orig_txn_id,
                            "person_id": orig_txn.from_id, "merchant_id": orig_txn.to_id,
                            "amount": orig_txn.amount, "payment_id": pid,
                        })

                # -- Risk: score exactly the eligible (>=2 owners) devices
                # with new activity today (same rule live_risk_loop.py uses).
                eligible = devices_with_sharers(g)
                todays_active = sorted({
                    t.device_id for t in self.engine.transactions
                    if t.day == day and t.kind in ("purchase", "payment_failure") and t.device_id
                })
                to_score = sorted(set(eligible) & set(todays_active))
                for device_id in to_score:
                    verdict = run_risk_for_device(g, device_id, investigate=False)
                    risk_decisions.append({
                        "device_id": device_id, "decision": verdict.decision,
                        "proposed_action": verdict.proposed_action,
                        "decision_score": verdict.decision_score, "reason": verdict.reason,
                    })
                    if verdict.decision in _BLOCKING_DECISIONS and device_id not in self.blocked_devices:
                        self.engine.block_device(device_id, day=day)
                        self.blocked_devices.add(device_id)
                        devices_blocked_today.append(device_id)
            finally:
                g.close()

            entry = {
                "day": day,
                "retries_attempted": retries_attempted,
                "recovery_decisions": recovery_decisions,
                "risk_decisions": risk_decisions,
                "new_failures": new_failures,
                "devices_blocked": devices_blocked_today,
                "total_transactions": len(self.engine.transactions),
                "ended": False,
            }
            self.log.append(entry)
            self.day += 1
            return entry


_env: TrumanEnvironment | None = None
_env_lock = threading.Lock()


def get_environment() -> TrumanEnvironment:
    global _env
    if _env is None:
        with _env_lock:
            if _env is None:
                _env = TrumanEnvironment()
    return _env
