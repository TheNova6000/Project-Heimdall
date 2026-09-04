"""
Domain bridge registry -- a bounded, honest implementation of
docs/NORTH_STAR.md Section 26 ("Domain Package Architecture") and Section 28
("The Research Engine Must Continuously Expand These Domains" / "Capability
Graph"), scoped to exactly what this repo actually has: three real, working
Simulation -> Heimdall bridges (Recovery, Risk, Controller) plus three real,
documented, NOT-YET-buildable ones (fraud, credit, loan).

WHAT THIS IS: a structured catalog. Registering a domain means constructing
one `DomainBridge` and calling `register_domain()` -- a well-defined,
discoverable, testable process, replacing what was previously one-off code
spread across `simulation_bridge.py` and `run_bridge.py` with no catalog of
its own. `capability_report.py` reads this registry and prints it in the
"Capability Graph" style Section 28 describes.

WHAT THIS IS NOT: this is not machine learning, not autonomous domain
discovery, and not self-modifying code. Nothing here scans code, infers a
new domain's fields from data, or decides on its own that a domain should
move from BLOCKED to BRIDGED. A human or agent reads the real, frozen
Heimdall code and Simulation/'s real output schema, writes a transform (or
documents why one can't be written yet), and calls `register_domain()`
explicitly. Section 28's own five-way vocabulary (SUPPORTED / PARTIAL /
UNKNOWN / MISSING / UNVERIFIED) describes a continuously-running research
engine this project does not have and does not claim to have; this registry
only ever reports two real, demonstrated states -- BRIDGED (a transform and
a real Heimdall entry point both exist and have been run) and BLOCKED (they
don't, for a stated, specific reason) -- because those are the only two
states this codebase can actually prove.

Existing bridge behavior is UNCHANGED by this module. `simulation_bridge.py`
and `run_bridge.py` are not imported or modified for their control flow;
this module only references their already-existing, already-working
functions by name, the same way any other caller would.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

# The commit this registry's field lists / blocked-reasons were verified
# against by reading the actual source named below -- not a fabricated
# timestamp. Update by hand (with a fresh `git rev-parse HEAD`) only when
# the underlying transform/agent code this registry describes actually
# changes; this is a plain string, not a real versioning system, same
# discipline as recovery/signals.py's RECOVERY_LOGIC_VERSION.
VERIFIED_AT_COMMIT = "ef268bae031c87074086dd2d44902af551f38992"

DomainStatus = Literal["BRIDGED", "BLOCKED"]


@dataclass(frozen=True)
class DomainBridge:
    """One catalog entry. Every field here is something a real reader could
    check against real code -- nothing is aspirational."""

    domain_name: str
    status: DomainStatus

    # For BRIDGED: a description naming the real, unmodified Heimdall
    # callable this domain's decisions come from (module path + function
    # name -- import it yourself to get the callable, this registry does
    # not re-export it to avoid a second, possibly-drifting reference).
    # For BLOCKED: the function that would eventually be called, read from
    # the relevant frozen code where one already exists (e.g. Controller's
    # own reconcile_settlement() shape suggests what a Loan equivalent
    # might look like), or "does not exist yet" stated plainly when no such
    # module exists in financial_system/ at all -- checked directly, not
    # guessed (confirmed at VERIFIED_AT_COMMIT: no financial_system/fraud/,
    # financial_system/credit/, or financial_system/loan/ package exists).
    heimdall_entry_point: str

    # What Truman/Simulation output the transform needs. For BRIDGED
    # domains: extracted directly from what simulation_bridge.py's
    # transform_simulation_output() actually reads today (verified by
    # reading that function, not invented). For BLOCKED domains: the
    # field-level design Simulation/docs/Research.md Part C already wrote
    # up for that mechanism -- named as MISSING, not invented fresh here.
    required_truman_fields: list[str] = field(default_factory=list)

    # BRIDGED only: the real transform callable. Recovery/Risk/Controller
    # all share ONE real transform function today
    # (simulation_bridge.transform_simulation_output) -- it is not
    # domain-separated in the existing code, and this registry does not
    # pretend otherwise by fabricating three separate functions; it points
    # all three at the one real function that actually produces their
    # input data, and names each domain's real *consuming* function
    # separately in heimdall_entry_point above.
    transform_fn: Optional[Callable] = None

    # BLOCKED only: precise, real reasoning -- reused verbatim (not
    # loosely rephrased) from bridges/README.md's own gap sections and
    # Simulation/docs/Research.md Part C's own "Why not built now" text.
    blocked_reason: Optional[str] = None

    # Concrete and real: the commit this entry's claims were verified
    # against, optionally with a pointer to the specific verification run
    # (a bridges/README.md section, a test name) -- never a bare timestamp.
    last_verified: str = ""

    def __post_init__(self) -> None:
        if self.status == "BRIDGED":
            if self.transform_fn is None:
                raise ValueError(f"{self.domain_name}: BRIDGED entries must set transform_fn")
            if self.blocked_reason is not None:
                raise ValueError(f"{self.domain_name}: BRIDGED entries must not set blocked_reason")
        elif self.status == "BLOCKED":
            if not self.blocked_reason:
                raise ValueError(f"{self.domain_name}: BLOCKED entries must set blocked_reason")
            if self.transform_fn is not None:
                raise ValueError(f"{self.domain_name}: BLOCKED entries must not set transform_fn")
        else:
            raise ValueError(f"{self.domain_name}: status must be BRIDGED or BLOCKED, got {self.status!r}")
        if not self.required_truman_fields:
            raise ValueError(f"{self.domain_name}: required_truman_fields must not be empty")
        if not self.last_verified:
            raise ValueError(f"{self.domain_name}: last_verified must not be empty")


# The registry itself -- a plain dict, domain_name -> DomainBridge. Not a
# database, not persisted, not self-updating: it is rebuilt by importing
# this module, exactly like any other Python module-level constant.
DOMAIN_REGISTRY: dict[str, DomainBridge] = {}


def register_domain(entry: DomainBridge, *, replace: bool = False) -> DomainBridge:
    """The one real extension point: registering domain N+1 means
    constructing a DomainBridge (declare required fields, point at a real
    transform + a real or 'does not exist yet' Heimdall entry point, state
    a real blocked_reason if blocked) and calling this function. Refuses a
    silent overwrite of an existing name unless replace=True, so a copy-paste
    typo can't quietly clobber an existing catalog entry."""
    if entry.domain_name in DOMAIN_REGISTRY and not replace:
        raise ValueError(
            f"domain {entry.domain_name!r} is already registered "
            f"(pass replace=True to intentionally overwrite it)"
        )
    DOMAIN_REGISTRY[entry.domain_name] = entry
    return entry


def get_domain(domain_name: str) -> DomainBridge:
    return DOMAIN_REGISTRY[domain_name]


def bridged_domains() -> list[DomainBridge]:
    return [d for d in DOMAIN_REGISTRY.values() if d.status == "BRIDGED"]


def blocked_domains() -> list[DomainBridge]:
    return [d for d in DOMAIN_REGISTRY.values() if d.status == "BLOCKED"]


# ---------------------------------------------------------------------------
# The three real, existing bridges (Recovery, Risk, Controller).
#
# Registering them here does not rewrite one byte of their transform logic
# -- simulation_bridge.py's transform_simulation_output() and each domain's
# real agent function (recovery_agent.run_recovery_for_payment,
# risk_agent.run_risk_for_device, controller.run_controller_for_settlement)
# are referenced by name only, imported lazily inside the functions below so
# importing financial_system.bridges.registry never has a side effect on
# financial_system/'s own module-import graph beyond what bridges/ already
# had.
# ---------------------------------------------------------------------------

def _transform_simulation_output(*args, **kwargs):
    from financial_system.bridges.simulation_bridge import transform_simulation_output
    return transform_simulation_output(*args, **kwargs)


register_domain(DomainBridge(
    domain_name="recovery",
    status="BRIDGED",
    heimdall_entry_point=(
        "financial_system.recovery.recovery_agent.run_recovery_for_payment(graph, payment_id, "
        "investigate=False) -- Heimdall's real, unmodified Phase 7 agent"
    ),
    required_truman_fields=[
        "transactions.csv: kind in {purchase, payment_failure} -> payments.csv: status "
        "('success'/'failed') -- recovery/signals.py's compute_recovery_signals() reads status directly",
        "transactions.csv: kind=='payment_failure' (Simulation's one real, mechanically-verified "
        "failure cause, balance_before<amount) -> payments.csv: failure_reason='insufficient_funds' "
        "-- the only FAILURE_TAXONOMY category recovery/signals.py can ever see from bridged data",
        "transactions.csv: transaction_id -> one Order per Payment (1:1, matching the real Heimdall "
        "dataset's own convention) -- recovery/signals.py's has_alternate_success/has_prior_failed_"
        "attempts sibling check walks belongs_to edges off this Order",
        "transactions.csv: from_id, to_id, amount, timestamp -> payments.csv: customer_id, "
        "merchant_id, amount, created_at/authorized_at/captured_at",
    ],
    transform_fn=_transform_simulation_output,
    last_verified=(
        f"commit {VERIFIED_AT_COMMIT}; bridges/README.md 'Real end-to-end run' "
        "(171 failed payments, decision distribution {'RETRY': 171})"
    ),
))

register_domain(DomainBridge(
    domain_name="risk",
    status="BRIDGED",
    heimdall_entry_point=(
        "financial_system.risk.runner.devices_with_sharers(graph) to select candidate Devices, then "
        "financial_system.risk.risk_agent.run_risk_for_device(graph, device_id, investigate=False) -- "
        "Heimdall's real, unmodified Phase 6 agent"
    ),
    required_truman_fields=[
        "devices.csv: device_id, owner_person_ids, fingerprint -- real Simulation Device data, read "
        "directly (not fabricated); risk/runner.py's devices_with_sharers() only ever scores a Device "
        "with >=2 distinct owning Customers",
        "transactions.csv: device_id (present on purchase/payment_failure rows) -> payments.csv: "
        "device_id -- the payer's own real device for that transaction, which risk/signals.py's "
        "compute_device_risk_signals() walks via the graph's used_device/uses edges to find shared "
        "devices and their burst/account-age signals",
    ],
    transform_fn=_transform_simulation_output,
    last_verified=(
        f"commit {VERIFIED_AT_COMMIT}; bridges/README.md 'Part 2: Risk' "
        "(41 devices with >=2 owners scored, decision distribution {'RELEASE': 35, 'REVIEW': 6}, "
        "decision_score range 0.095-0.550)"
    ),
))

register_domain(DomainBridge(
    domain_name="controller",
    status="BRIDGED",
    heimdall_entry_point=(
        "financial_system.reconciliation.controller.run_controller_for_settlement(graph, settlement_id, "
        "investigate=False) -- Heimdall's real, unmodified Phase 5 agent, whose core arithmetic lives in "
        "reconciliation.deterministic.reconcile_settlement()"
    ),
    required_truman_fields=[
        "transactions.csv: kind=='settlement' rows (transaction_id, to_id=merchant_id, amount, "
        "timestamp) -> settlements.csv (settlement_id, merchant_id, settlement_date, gross_amount, "
        "net_amount) + bank_transactions.csv (one matching BankTransaction, honestly identical amount) "
        "-- reconcile_settlement() reads Settlement.net_amount and sums the amounts of BankTransactions "
        "reached via the resolved deposited_as edge",
        "transactions.csv: kind=='purchase' rows from the calendar day immediately before a "
        "settlement's own date, grouped by merchant (Simulation's own T+1 sweep timing, "
        "world/engine.py's _run_settlement) -> settlement_payments.csv (settlement_id, payment_id "
        "pairs) -- reconcile_settlement() reads these via the settlement's contains edges (duplicate-"
        "line-item check only)",
    ],
    transform_fn=_transform_simulation_output,
    last_verified=(
        f"commit {VERIFIED_AT_COMMIT}; bridges/README.md 'Part 3: Controller' "
        "(1770 settlements, decision distribution {'PASS': 1770}, 1770/1770 deterministic bank "
        "matches, settlement_sum_check_mismatches=0)"
    ),
))


# ---------------------------------------------------------------------------
# The three real, documented BLOCKED domains -- from
# Simulation/docs/Research.md Part C's own field-level designs. Reasoning
# reused verbatim from Research.md and bridges/README.md, not rephrased.
# ---------------------------------------------------------------------------

register_domain(DomainBridge(
    domain_name="fraud",
    status="BLOCKED",
    heimdall_entry_point=(
        "does not exist yet -- no financial_system/fraud/ package at all "
        f"(confirmed by directory listing at commit {VERIFIED_AT_COMMIT}); financial_system/risk/ "
        "handles shared-device network signal only, not a transaction-level fraud_attempt/"
        "is_fraudulent concept"
    ),
    required_truman_fields=[
        "Person.fraud_propensity: a new hidden trait -- Research.md Part C.1, not visible to any "
        "decision logic (would leak into spend-probability decisions otherwise)",
        "Transaction.kind new values fraud_attempt (and fraud_blocked/fraud_succeeded) -- not in "
        "Simulation's actual kind vocabulary today (purchase, payment_failure, salary, settlement, "
        "household_sweep, savings_sweep, org_funding)",
        "Transaction.is_fraudulent: a new boolean flag distinguishing a fraud transaction from an "
        "ordinary purchase/payment_failure -- does not exist",
        "Merchant.category-linked risk multiplier, used behaviorally -- Research.md Part C.1 notes "
        "Merchant.category already exists but is a cosmetic placeholder only (Phase 1's Memory.md); "
        "this would be the first mechanism to actually use it",
        "a new causal 'compromise event' concept -- fraud is not the account owner's own decision, so "
        "there is no existing agent-state field this can derive from at all",
    ],
    blocked_reason=(
        "Simulation/ does not model fraud at all, by explicit, repeated design choice "
        "(Simulation/docs/Research.md Part C.1; bridges/README.md's own Risk section: 'No fraud-ring "
        "mechanism was added anywhere -- Simulation/ still does not model fraud, by explicit, repeated "
        "design choice'). Fraud needs a genuinely new causal object (an account 'compromise event', not "
        "just an existing Person's own decision) that doesn't fit the existing 'every agent decision is "
        "a function of that agent's own visible state' model cleanly -- it needs either a new synthetic "
        "attacker agent or a special-cased event generator, either of which Research.md Part C.1 "
        "explicitly reserves for 'a dedicated, reviewed Phase 4-class effort', not built here."
    ),
    last_verified=f"commit {VERIFIED_AT_COMMIT}; Simulation/docs/Research.md Part C.1 read directly",
))

register_domain(DomainBridge(
    domain_name="credit",
    status="BLOCKED",
    heimdall_entry_point=(
        f"does not exist yet -- no financial_system/credit/ package at all (confirmed by directory "
        f"listing at commit {VERIFIED_AT_COMMIT})"
    ),
    required_truman_fields=[
        "Person.credit_score: a new field, 300-850 range (matching FICO/VantageScore 4.0's stated "
        "ranges per Research.md Part A §3) -- does not exist in persons.csv",
        "a new CreditEvent (or Event extension) capturing what changed a score and by how much, so "
        "score changes stay causally traceable -- does not exist",
    ],
    blocked_reason=(
        "credit_score needs a genuinely new piece of PERSISTENT agent state that, unlike balance, "
        "doesn't reset/reconcile against any ledger -- Research.md Part C.2: 'there's no natural "
        "\"debit/credit\" pair for a credit-score change the way Phase 2's double-entry model requires "
        "for money movements, so it would be the first agent field in this codebase that lives entirely "
        "outside the ledger-invariant discipline Phase 2 established. That's a real architectural "
        "decision ... worth a dedicated review, not something to bolt on inside a narrow research task.'"
    ),
    last_verified=f"commit {VERIFIED_AT_COMMIT}; Simulation/docs/Research.md Part C.2 read directly",
))

register_domain(DomainBridge(
    domain_name="loan",
    status="BLOCKED",
    heimdall_entry_point=(
        f"does not exist yet -- no financial_system/loan/ package at all (confirmed by directory "
        f"listing at commit {VERIFIED_AT_COMMIT})"
    ),
    required_truman_fields=[
        "a new Loan dataclass: loan_id, person_id, principal, interest_rate, origination_day, "
        "term_days, outstanding_balance, status (current/delinquent/defaulted/paid-off) -- does not "
        "exist",
        "Bank: a loans registry parallel to the existing accounts dict -- does not exist -- plus "
        "(Research.md Part C.3) a real 'loanable funds' constraint modeled on Basel-style capital-"
        "adequacy concepts, not a pre-2020 fractional-reserve model, if ever built",
        "credit_score (from the credit domain above) as an input to interest_rate = base_rate + "
        "risk_spread(person) -- loan is itself blocked on credit being blocked first",
    ],
    blocked_reason=(
        "Loan needs a new persistent liability-side object that interacts with the existing "
        "double-entry ledger in a way Phase 2 never designed for -- Research.md Part C.3: 'a loan "
        "disbursement is a new money-creation event from the bank's perspective, conceptually different "
        "from fund_external's \"external source, e.g. salary\" pattern -- modeling it honestly means "
        "deciding whether/how a Bank's lending capacity is itself constrained'. Explicitly named as the "
        "largest of the three Part C proposals; not built."
    ),
    last_verified=f"commit {VERIFIED_AT_COMMIT}; Simulation/docs/Research.md Part C.3 read directly",
))
