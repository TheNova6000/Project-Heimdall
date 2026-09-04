"""
Demonstration domain: settlement-coverage check.

Proves `financial_system.bridges.registry` is a REAL extension point, not a
static list -- registers a genuinely new, fourth "domain" through the exact
same mechanism used for Recovery/Risk/Controller in registry.py: declare
required fields, write a small real transform, call register_domain(), run
it through capability_report.py, get real output.

This is deliberately NOT one of Heimdall's three real agent decision
domains -- it produces no AgentVerdict, calls no Recovery/Risk/Controller
agent function, and is not itself a claim that a fourth Heimdall domain now
exists. It is a basic, count-based reconciliation summary chosen because it
needs ZERO new Simulation/ or Heimdall work: `simulation_bridge.py` already
writes everything this needs (payments.csv, settlement_payments.csv) as
part of bridging Recovery and Controller. That is itself the point being
demonstrated -- not every new registry entry requires new upstream data;
some just need a new query over data the bridge already produces.

Question this answers: of all successful (bridged) purchases, what
fraction were actually swept into a settlement batch? A purchase from the
last calendar day of a run is expected to be uncovered (no next-day
settlement exists yet in a finite simulation window) -- an honest boundary
effect, not a bug, named here rather than silently ignored.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CoverageReport:
    successful_payments: int
    payments_covered_by_a_settlement: int

    @property
    def coverage_rate(self) -> float:
        return (self.payments_covered_by_a_settlement / self.successful_payments
                if self.successful_payments else float("nan"))


def compute_settlement_coverage(bridge_raw_dir: Path) -> CoverageReport:
    """Reads the bridge's own already-written raw CSVs -- payments.csv and
    settlement_payments.csv, both written by simulation_bridge.py's
    existing transform_simulation_output() for Recovery/Controller's own
    use -- and counts how many successful payments were actually covered by
    a settlement batch. Pure read of already-bridged output; imports
    nothing from Simulation/ or financial_system/'s decision code, touches
    no file anywhere."""
    bridge_raw_dir = Path(bridge_raw_dir)
    with open(bridge_raw_dir / "payments.csv", newline="", encoding="utf-8") as f:
        payments = list(csv.DictReader(f))
    with open(bridge_raw_dir / "settlement_payments.csv", newline="", encoding="utf-8") as f:
        settlement_payments = list(csv.DictReader(f))

    successful_ids = {p["payment_id"] for p in payments if p["status"] == "success"}
    covered_ids = {row["payment_id"] for row in settlement_payments} & successful_ids

    return CoverageReport(
        successful_payments=len(successful_ids),
        payments_covered_by_a_settlement=len(covered_ids),
    )
