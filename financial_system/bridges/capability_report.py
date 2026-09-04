"""
Capability report: prints the real DomainBridge registry state -- which
domains are BRIDGED (with a live one-line summary computed from an actual
bridge run, not a hardcoded/stale number) and which are BLOCKED (with the
precise, real reason), in the "Capability Graph" style
docs/NORTH_STAR.md Section 28 describes -- adapted to this project's own
real, demonstrated two-state vocabulary (BRIDGED / BLOCKED), not Section
28's aspirational five-way SUPPORTED / PARTIAL / UNKNOWN / MISSING /
UNVERIFIED vocabulary, which describes a continuously-running research
engine this project does not have and is not claiming to have.

This module also registers ONE additional, genuinely new domain
("coverage") through the exact same `register_domain()` mechanism the six
real domains use in registry.py -- see coverage_check.py's docstring for
why this specific example was chosen and what it deliberately is/isn't.
Doing the registration here (in a separate module that only imports
registry.py's public API) rather than inside registry.py itself is the
point: it proves a caller outside the registry's own module can extend it,
not just that the registry's author can.

Run directly:
  python -m financial_system.bridges.capability_report <simulation_outdir> [bridge_outdir]
    -- runs a real bridge pass (via run_bridge.run_bridge, unmodified) and
       reports against its real output.

Or import build_report(bridge_result, raw_dir) to report against an
already-completed run_bridge() result without re-running anything.

Not machine learning, not autonomous, not self-modifying: see
registry.py's module docstring for the same disclaimer, which applies
here too.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from financial_system.bridges.coverage_check import compute_settlement_coverage
from financial_system.bridges.registry import (
    DOMAIN_REGISTRY, DomainBridge, VERIFIED_AT_COMMIT, bridged_domains, blocked_domains, register_domain,
)

# --- Registering a NEW domain (item 5: prove the mechanism) ----------------
# This is the whole demonstration: three lines of real work (declare
# required fields, name a real transform, call register_domain()) is all
# it takes to add domain N+1 to the catalog. No other file needed to
# change for this to work -- not registry.py, not simulation_bridge.py, not
# run_bridge.py.
register_domain(DomainBridge(
    domain_name="coverage",
    status="BRIDGED",
    heimdall_entry_point=(
        "none -- this is a bridge-side deterministic check, not a Heimdall agent decision (it produces "
        "no AgentVerdict and calls no recovery_agent/risk_agent/controller function). Registered "
        "specifically to demonstrate the registry's extension mechanism (task item 5), not to claim a "
        "fourth real Heimdall decision domain exists."
    ),
    required_truman_fields=[
        "transactions.csv: kind=='purchase' rows -- already bridged into payments.csv (status=='success') "
        "by the existing transform; no new Simulation/ field needed",
        "transactions.csv: kind=='settlement' rows' T+1 grouping -- already bridged into "
        "settlement_payments.csv by the existing Controller transform; no new Simulation/ field needed",
    ],
    transform_fn=compute_settlement_coverage,
    last_verified=f"commit {VERIFIED_AT_COMMIT}; financial_system/bridges/test_registry.py",
))


def _format_bridged(entry: DomainBridge, summary_line: str) -> str:
    lines = [
        f"{entry.domain_name}  -- BRIDGED",
        f"  Heimdall entry point: {entry.heimdall_entry_point}",
        f"  Required Truman fields ({len(entry.required_truman_fields)}):",
    ]
    for f in entry.required_truman_fields:
        lines.append(f"    - {f}")
    lines.append(f"  Last verified: {entry.last_verified}")
    lines.append(f"  Live run summary: {summary_line}")
    return "\n".join(lines)


def _format_blocked(entry: DomainBridge) -> str:
    lines = [
        f"{entry.domain_name}  -- BLOCKED",
        f"  Heimdall entry point: {entry.heimdall_entry_point}",
        f"  Required Truman fields, all MISSING ({len(entry.required_truman_fields)}):",
    ]
    for f in entry.required_truman_fields:
        lines.append(f"    - {f}")
    lines.append(f"  Blocked reason: {entry.blocked_reason}")
    lines.append(f"  Last verified: {entry.last_verified}")
    return "\n".join(lines)


def build_report(bridge_result: Optional[dict] = None, raw_dir: Optional[Path] = None) -> str:
    """Builds the full capability report text.

    bridge_result: the dict returned by run_bridge.run_bridge(), used to
    compute LIVE one-line summaries for recovery/risk/controller from real
    run numbers instead of hardcoded ones. raw_dir: the bridge's own
    raw/ output directory (bridge_dir/raw), used to compute the live
    "coverage" summary. Either or both may be omitted -- summaries fall
    back to "(no live run result supplied; see <domain>.last_verified for "
    "the last real verified numbers)" when omitted, never to a fabricated
    number.
    """
    lines = [
        "=== Heimdall Domain Bridge Registry -- Capability Report ===",
        "(A structured catalog, not an autonomous or self-learning system --",
        " see financial_system/bridges/registry.py's module docstring.)",
        "",
    ]

    bridged = bridged_domains()
    blocked = blocked_domains()
    lines.append(f"BRIDGED ({len(bridged)})")
    lines.append("-" * 11)
    for entry in bridged:
        summary = f"(no live run result supplied; see last_verified: {entry.last_verified})"
        if entry.domain_name == "recovery" and bridge_result is not None:
            n = len(bridge_result["failed_payment_ids"])
            summary = (
                f"{n} failed payments; decision distribution {dict(bridge_result['decisions'])}; "
                f"proposed_action distribution {dict(bridge_result['proposed_actions'])}"
            )
        elif entry.domain_name == "risk" and bridge_result is not None:
            n = len(bridge_result["shared_device_ids"])
            scores = [v.decision_score for v in bridge_result["risk_verdicts"]]
            score_range = f"{min(scores):.3f}..{max(scores):.3f}" if scores else "n/a"
            summary = (
                f"{n} devices with >=2 owners scored; decision distribution "
                f"{dict(bridge_result['risk_decisions'])}; decision_score range {score_range}"
            )
        elif entry.domain_name == "controller" and bridge_result is not None:
            n = len(bridge_result["settlement_ids"])
            summary = f"{n} settlements; decision distribution {dict(bridge_result['controller_decisions'])}"
        elif entry.domain_name == "coverage" and raw_dir is not None:
            cov = compute_settlement_coverage(raw_dir)
            summary = (
                f"{cov.successful_payments} successful payments; "
                f"{cov.payments_covered_by_a_settlement} covered by a settlement "
                f"({cov.coverage_rate:.1%})"
            )
        lines.append(_format_bridged(entry, summary))
        lines.append("")

    lines.append(f"BLOCKED ({len(blocked)})")
    lines.append("-" * 10)
    for entry in blocked:
        lines.append(_format_blocked(entry))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: python -m financial_system.bridges.capability_report <simulation_outdir> [bridge_outdir]"
        )
    from financial_system.bridges.run_bridge import DEFAULT_BRIDGE_DIR, run_bridge

    sim_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BRIDGE_DIR
    result = run_bridge(sim_dir, out_dir)
    print("\n" + build_report(result, out_dir / "raw"))
