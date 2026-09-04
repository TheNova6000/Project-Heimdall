"""
Live Risk loop: closes Risk's one-way bridge into a REAL, in-loop
enforcement loop -- the Risk-domain sibling of `live_recovery_loop.py`
(read that module's own docstring and `financial_system/bridges/README.md`'s
"Live Recovery loop" section FIRST; this module copies its architecture
precisely and only restates what's genuinely different below).

WHAT THIS IS (bounded, honestly, by design -- same convention as the
Recovery live loop): a genuinely SMALL Simulation/ world is driven
day-by-day. After EVERY simulated day, the world's ENTIRE real
transaction stream so far is re-ingested through Heimdall's real Phase
1/2/3 pipeline (unmodified), and every real Device with >=2 distinct
owning Customers that had NEW payment activity that day -- never a
sample, never a filtered subset of the ELIGIBLE devices -- gets a real
decision from Heimdall's real, unmodified
`risk.risk_agent.run_risk_for_device()`. If that decision is REVIEW or
HOLD (Risk's own two non-RELEASE tiers -- see "Decision vocabulary"
below), the device is REALLY blocked via the new
`SimulationEngine.block_device()` method (Simulation/world/engine.py),
and every later purchase attempt from that device is REALLY prevented by
`_maybe_attempt_purchase()`'s own new device-blocked check -- a
mechanical consequence, not a log line (see "Real, traced causal effect"
below).

WHY "for devices with new activity that day", not "every eligible device
every day": a Device's eligibility (>=2 distinct owner_person_ids) is
fixed at world-generation time (Simulation/world/engine.py's
device-assignment pass, run once in `_build_world()`, long before `run()`
starts) -- it never changes during a run. What DOES change day to day is
the device's own payment history, which is exactly what Risk's real
signals (`risk/signals.py`: burst density within a 60-minute window,
account age, sharer count) are computed over. Re-scoring a device on a
day it had zero new purchase/payment_failure activity would read the
exact same signals as its last scoring and can only ever repeat the same
verdict -- wasted, redundant Heimdall calls with zero chance of a new
finding. Scoring exactly the eligible devices with new activity that day
is therefore both the honest reading of "which devices need re-evaluating
right now" and the tractable one (see "Checkpoint frequency" below).

DECISION VOCABULARY (confirmed by reading `risk/risk_agent.py` and
`risk/scoring.py` directly, not assumed): `score_signals()` produces a
tier via `risk_tier()` (LOW/MEDIUM/HIGH, thresholds 0.3/0.6), and
`risk_agent.py`'s own `_TIER_DECISION` maps LOW->RELEASE, MEDIUM->REVIEW,
HIGH->HOLD. This loop blocks on REVIEW and HOLD alike (`decision !=
"RELEASE"`) -- both are Risk's own real "this needs a human/action, not a
silent pass" verdicts, RELEASE is the only "nothing to do" tier.

DOES RISK EVER CALL AN LLM? No, by construction, same discipline as the
Recovery loop's own equivalent finding: this loop's only call site passes
`investigate=False` unconditionally (`run_risk_for_device(graph,
device_id, investigate=False)`). Reading `risk_agent.py`'s
`run_risk_for_device()` directly: Discovery.AI's `investigate_evidence()`
is only ever called when BOTH `tier == "HIGH"` AND `investigate` is
True -- confirmed directly, not guessed. `test_live_risk_loop.py::
test_no_llm_calls_ever` proves this from real output (every decision's
`investigation_confidence` is `None`).

REAL, TRACED CAUSAL EFFECT (not a cosmetic "would have blocked" claim):
a blocked device's `_maybe_attempt_purchase()` failure is recorded with
`balance_before` -- the person's REAL balance at the moment of the
(prevented) attempt. `world/agents/bank.py`'s `post_transfer()` succeeds
if and only if `balance_before >= amount` (confirmed by reading it
directly -- the enforcement point for Rules.md #7, "no negative
balances"). So for every blocked-device failure this loop's report
records, `balance_before >= amount` is a PROVABLE, deterministic fact
about what `post_transfer()` would have returned had the device not been
blocked -- no separate counterfactual run is needed to know, for that one
transaction, whether the block was consequential (would have succeeded)
or inconsequential (would have failed anyway on insufficient funds).
`run_live_risk_loop`'s own report exposes this per blocked attempt
(`BlockedPurchaseAttempt.would_have_succeeded`); `test_live_risk_loop.py`
additionally runs a REAL counterfactual (same seed, `block_device()`
never called) and diffs the affected person's own balance trajectory
after the block point, for a second, independent confirmation -- see that
test and the README's own "Real end-to-end run" section for real numbers.

DETERMINISM (the property this whole design exists to protect -- same
argument structure as live_recovery_loop.py's own "Determinism" section):
same seed + same config -> byte-identical output, INCLUDING which devices
get blocked, on which day, and every resulting blocked-purchase failure.
This holds because:
  1. Heimdall's own decision logic is a pure function of graph state (no
     RNG, no LLM -- confirmed above).
  2. Every checkpoint's eligible-with-new-activity devices are scored in a
     FIXED order (sorted by device_id -- `risk.runner.devices_with_sharers()`
     itself already returns a sorted list; this loop additionally
     intersects it with a sorted set of today's active device_ids and
     iterates the sorted intersection, never dict/set iteration order).
  3. `block_device()` calls happen in a FIXED position in the day loop
     (immediately AFTER that day's own `run_one_tick()` and AFTER that
     day's Risk checkpoint has scored every active eligible device --
     never interleaved with, or ahead of, that day's own core RNG draws),
     in the SAME fixed per-device order the scoring loop above already
     used.
  4. `block_device()` itself draws ZERO randomness (see its own
     docstring: it uses a fixed canonical timestamp, deliberately, since a
     block is a systemic Risk-system decision, not a person's own
     randomly-timed activity) -- calling it any number of times in any
     order cannot perturb `engine.rng`'s own draw sequence at all. The
     ONLY randomness anywhere in this loop is Simulation's own single
     seeded `engine.rng`, consumed exactly where a normal run already
     consumes it (`_maybe_attempt_purchase()`'s own per-person draws,
     unperturbed by this loop's existence -- see engine.py's own proof
     that the device-blocked check is a no-op unless `blocked_devices` is
     non-empty).

CHECKPOINT FREQUENCY: every single simulated day, same choice
live_recovery_loop.py made and for the same reason -- at this loop's own
small population (see "Population choice" below), a full daily rebuild is
cheap (measured below), so no coarser batching was needed to keep this
tractable. This is also the finest granularity that could possibly matter
here: Risk's signals only change on a day a device had new activity, and
this loop already only re-scores exactly those devices, so checkpointing
less often than daily would only delay a REAL verdict from being acted on
-- letting more (needlessly unprotected) purchases through -- for no
performance benefit at this scale.

POPULATION CHOICE: this loop needs Risk to have something real to score,
i.e. real household-shared Devices (`owner_person_ids` with >=2 entries)
-- see `Simulation/docs/Memory.md`'s "Device" section: the ONE legitimate
sharing mechanism this simulation models
(`DEVICE_HOUSEHOLD_SHARING_FRACTION = 0.3`). The existing batch bridge
needed population=300 to produce 41 shared devices (bridges/README.md,
"Part 2: Risk"); at the Recovery live loop's own population=20, a quick
measurement (seed=42, same days/banks/merchants) produced only 2 shared
devices -- too thin to reliably produce even one REVIEW verdict every
run. population=30 (same seed) reliably produces 5 shared devices, of
which 2 reach REVIEW (score 0.31, 0.489) in this task's own real run
below -- the smallest population from a quick seed=42 sweep (20/30/40/50
tested) that reliably clears "a few real shared devices AND at least one
real REVIEW verdict", so this loop defaults to population=30, keeping the
SAME small-canvas philosophy as the Recovery loop (the bank/Risk agent
watches its whole small world's real activity, nothing sampled or
cherry-picked out of a larger population) rather than reusing
population=20 unmodified just because Recovery already used it.

SCOPE: Risk only. Recovery is already done (live_recovery_loop.py, a
SEPARATE module, untouched by this task); Controller reacting live is
still real future work, not attempted here. This loop does not call
Recovery's own live loop or interact with it in any way -- running both
loops simultaneously against the same world (so that a device-blocked
`payment_failure` could also be evaluated by Recovery, which would
currently misclassify it as `insufficient_funds` via
`simulation_bridge.py`'s own fixed `SIMULATION_FAILURE_REASON` constant,
since that bridge module is off-limits and unmodified by this task) is
explicitly out of scope and not attempted -- see the README's "Honest
scope" section for this caveat stated plainly.
"""
from __future__ import annotations

import datetime
import json
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
from financial_system.risk.risk_agent import run_risk_for_device
from financial_system.risk.runner import devices_with_sharers

# Risk's own two non-RELEASE tiers (risk_agent.py's _TIER_DECISION,
# confirmed by reading it directly) -- both trigger a real block_device()
# call. RELEASE (LOW tier) is the only "nothing to do" verdict.
_BLOCKING_DECISIONS = {"REVIEW", "HOLD"}


@dataclass
class RiskDecisionRecord:
    device_id: str
    day_evaluated: int
    decision: str
    proposed_action: str
    decision_score: float
    reason: str
    n_sharers: int
    sharer_customer_ids: list  # verdict.affected_entities -- real Customer ids sharing this device
    # AgentVerdict.investigation_confidence -- always None here, same reason
    # (and same "kept, not just asserted" discipline) as
    # live_recovery_loop.py's DecisionRecord: this loop always calls
    # run_risk_for_device(..., investigate=False), and risk_agent.py's own
    # code only ever calls Discovery.AI when BOTH investigate=True AND
    # tier=="HIGH" -- see this module's own "DOES RISK EVER CALL AN LLM?"
    # section. A test proves this from real output, not from trusting the
    # call site.
    investigation_confidence: float | None = None


@dataclass
class BlockedPurchaseAttempt:
    """One real `_maybe_attempt_purchase()` call that was mechanically
    prevented because the payer's resolved device was blocked -- read
    directly off the real Transaction/Event the engine recorded, not
    inferred. `would_have_succeeded` is a provable fact (see module
    docstring, "REAL, TRACED CAUSAL EFFECT"): `post_transfer()` succeeds
    iff `balance_before >= amount`, so this is computed the same way,
    directly from the same two real recorded numbers -- not a guess."""
    transaction_id: str
    person_id: str
    merchant_id: str
    device_id: str
    day: int
    amount: float
    balance_before: float

    @property
    def would_have_succeeded(self) -> bool:
        return self.balance_before >= self.amount


@dataclass
class LiveRiskLoopReport:
    seed: int
    population: int
    days: int
    checkpoints_run: int
    total_transactions_final: int
    devices_with_sharers_total: int = 0  # as of the run's own last checkpoint
    decisions: list = field(default_factory=list)               # list[RiskDecisionRecord]
    devices_blocked: list = field(default_factory=list)         # list[str], in the order block_device() was called
    blocked_purchase_attempts: list = field(default_factory=list)  # list[BlockedPurchaseAttempt]

    @property
    def decision_counts(self) -> dict:
        counts: dict[str, int] = {}
        for d in self.decisions:
            counts[d.decision] = counts.get(d.decision, 0) + 1
        return counts

    @property
    def blocked_attempts_would_have_succeeded(self) -> int:
        return sum(1 for a in self.blocked_purchase_attempts if a.would_have_succeeded)


def run_live_risk_loop(
    seed: int,
    population: int,
    banks: int,
    merchants: int,
    days: int,
    start_date: datetime.date,
    work_dir: Path,
) -> LiveRiskLoopReport:
    """
    Drives a fresh SimulationEngine day-by-day. After EVERY simulated day,
    rebuilds Heimdall's real financial_state store + graph from the
    world's full transaction history so far (see module docstring -- this
    is tractable daily specifically because the canvas is small), and
    calls Heimdall's real `run_risk_for_device()` on every real Device
    that is (a) shared by >=2 distinct Customers (`devices_with_sharers`,
    Risk's own real eligibility rule) AND (b) had new purchase/
    payment_failure activity on this simulated day. Every REVIEW/HOLD
    verdict gets a real `block_device()` call, which takes effect starting
    the NEXT simulated day's purchase attempts (see `block_device()`'s own
    docstring for exactly why: it is always called AFTER that day's own
    `run_one_tick()`).
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

    blocked_so_far: set[str] = set()  # devices already block_device()'d -- never called twice for the same device

    report = LiveRiskLoopReport(
        seed=seed, population=population, days=days, checkpoints_run=0,
        total_transactions_final=0,
    )

    for day in range(days):
        # -- 1. Run this simulated day, exactly as run() would. Fixed
        # position: block_device() calls from a PRIOR iteration of this
        # loop already happened before this call (see step 3 below), so
        # any device blocked as of a previous checkpoint is already
        # consulted by this day's own _maybe_attempt_purchase() calls --
        # a block always protects the day AFTER it was decided, never
        # retroactively (see block_device()'s own docstring).
        events_before = len(engine.events)
        engine.run_one_tick()

        # -- 2. Checkpoint: re-ingest the world's full history so far
        # through Heimdall's real, unmodified Phase 1/2/3 pipeline (same
        # calls live_recovery_loop.py's own checkpoint makes, reused here
        # too).
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

        # -- 3. Score exactly the eligible (>=2 owners) devices with NEW
        # activity today -- see module docstring, "WHY 'for devices with
        # new activity that day'". Both sets are built/sorted
        # deterministically: devices_with_sharers(graph) already returns a
        # sorted list; today's active device_ids come directly from the
        # live engine's own transaction records for `day` (never from the
        # bridge's transformed CSV, same discipline live_recovery_loop.py
        # uses for its own original_txn lookups), sorted before use.
        eligible = devices_with_sharers(graph)
        todays_active_device_ids = sorted({
            t.device_id for t in engine.transactions
            if t.day == day and t.kind in ("purchase", "payment_failure") and t.device_id
        })
        to_score = sorted(set(eligible) & set(todays_active_device_ids))
        report.devices_with_sharers_total = len(eligible)

        for device_id in to_score:
            verdict = run_risk_for_device(graph, device_id, investigate=False)
            report.decisions.append(RiskDecisionRecord(
                device_id=device_id, day_evaluated=day, decision=verdict.decision,
                proposed_action=verdict.proposed_action, decision_score=verdict.decision_score,
                reason=verdict.reason, n_sharers=int(verdict.metrics.get("n_sharers", 0)),
                sharer_customer_ids=sorted(verdict.affected_entities),
                investigation_confidence=verdict.investigation_confidence,
            ))

            if verdict.decision in _BLOCKING_DECISIONS and device_id not in blocked_so_far:
                engine.block_device(device_id, day=day)
                blocked_so_far.add(device_id)
                report.devices_blocked.append(device_id)

        # Close every sqlite connection opened this checkpoint before the
        # next day's checkpoint tries to unlink() and rebuild the same db
        # paths -- required on Windows (same reason live_recovery_loop.py
        # does this).
        store.close()
        graph_state.close()
        graph.close()

        # -- 4. Trace real blocked-purchase preventions that happened
        # during THIS day's run_one_tick() (step 1) -- only possible once a
        # PRIOR day's checkpoint has already blocked a device (see the
        # fixed-position note on step 1 above). Read directly off the
        # engine's own Event log, filtered to exactly the event_type
        # `_maybe_attempt_purchase()`'s device-blocked branch emits
        # (`purchase_blocked_device`) -- never a Heimdall-side inference.
        for ev in engine.events[events_before:]:
            if ev.event_type != "purchase_blocked_device":
                continue
            payload = json.loads(ev.payload)
            report.blocked_purchase_attempts.append(BlockedPurchaseAttempt(
                transaction_id=payload["transaction_id"], person_id=payload["from_id"],
                merchant_id=payload["to_id"], device_id=engine.person_device[payload["from_id"]],
                day=day, amount=payload["amount"], balance_before=payload["balance_before"],
            ))

    report.total_transactions_final = len(engine.transactions)
    return report


def _default_work_dir() -> Path:
    return Path(__file__).resolve().parent / "live_risk_bridge_output"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Live Risk loop (Simulation/ <-> Heimdall, in-loop device blocking)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--population", type=int, default=30)
    parser.add_argument("--banks", type=int, default=2)
    parser.add_argument("--merchants", type=int, default=4)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--start-date", type=str, default="2026-01-01")
    parser.add_argument("--work-dir", type=str, default=str(_default_work_dir()))
    args = parser.parse_args()

    import time
    t0 = time.time()
    result = run_live_risk_loop(
        seed=args.seed, population=args.population, banks=args.banks,
        merchants=args.merchants, days=args.days,
        start_date=datetime.date.fromisoformat(args.start_date),
        work_dir=Path(args.work_dir),
    )
    elapsed = time.time() - t0

    print(f"LIVE RISK LOOP: seed={args.seed} population={args.population} "
          f"banks={args.banks} merchants={args.merchants} days={args.days}")
    print(f"  wall-clock time: {elapsed:.2f}s ({result.checkpoints_run} daily checkpoints)")
    print(f"  total transactions (final): {result.total_transactions_final}")
    print(f"  devices with >=2 owners (as of last checkpoint): {result.devices_with_sharers_total}")
    print(f"  Risk decisions made: {len(result.decisions)}  {result.decision_counts}")
    print(f"  devices blocked: {len(result.devices_blocked)}  {result.devices_blocked}")
    print(f"  blocked purchase attempts (real, prevented): {len(result.blocked_purchase_attempts)}")
    print(f"    of which would have SUCCEEDED if not blocked (balance_before >= amount): "
          f"{result.blocked_attempts_would_have_succeeded}")
    for a in result.blocked_purchase_attempts:
        print(f"    day={a.day} txn={a.transaction_id} person={a.person_id} device={a.device_id} "
              f"amount={a.amount:.2f} balance_before={a.balance_before:.2f} "
              f"would_have_succeeded={a.would_have_succeeded}")
