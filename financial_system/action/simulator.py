"""
Action execution + verification -- both simulated, per Rules.md: nothing in
this project calls a real payment/refund/bank API.

execute_action() is strictly policy-gated: it never decides for itself
whether an action is allowed, only whether policy already authorized it.

simulate_gateway_response() stands in for a real payment gateway's response
to a retry -- the ONE place in this module that reads
ground_truth/recovery_labels.csv. This is the environment being simulated,
not the agent: Recovery's own decision logic (recovery/signals.py,
recovery/recovery_agent.py) never touches this file or this function, and
never sees retry_would_succeed. A test harness mocking a gateway response is
a standard, honest pattern -- it's categorically different from an agent
reading its own answer key to decide what to do (Rules.md's actual
prohibition), and this module is exactly the harness/scoring-adjacent code
that rule already carves out.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from financial_system.policy.engine import PolicyDecision
from financial_system.verdict import AgentVerdict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RECOVERY_GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "recovery_labels.csv"


@lru_cache(maxsize=1)
def _recovery_outcomes() -> dict[str, bool]:
    with open(RECOVERY_GT_PATH, newline="", encoding="utf-8") as f:
        return {row["payment_id"]: row["retry_would_succeed"] == "True" for row in csv.DictReader(f)}


def execute_action(verdict: AgentVerdict, policy_decision: PolicyDecision) -> tuple[bool, str, str]:
    """Returns (executed, action_taken, log). Gated ONLY on policy_decision.outcome
    -- an unauthorized action never executes, regardless of what the verdict proposed."""
    if policy_decision.outcome != "ALLOW":
        return False, "NONE", f"not executed -- policy outcome was {policy_decision.outcome}, not ALLOW"
    action = policy_decision.authorized_action or "NONE"
    return True, action, f"SIMULATED: executed {action} for {verdict.subject} (no real API called)"


def simulate_gateway_response(payment_id: str) -> bool | None:
    """The one ground-truth read in the whole action/verification pipeline --
    standing in for a real gateway's response to a retry. Returns None if
    this payment has no recorded outcome (nothing to simulate against)."""
    return _recovery_outcomes().get(payment_id)


def verify_retry(payment_id: str) -> tuple[str, str]:
    """Verifies against the FINANCIAL STATE the (simulated) action produced --
    not 'the API returned 200'. Here that state is the simulated gateway's
    outcome; a real deployment would re-read the payment's actual status."""
    outcome = simulate_gateway_response(payment_id)
    if outcome is None:
        return "FAILURE", "no simulated outcome available for this payment"
    if outcome:
        return "SUCCESS", "simulated gateway confirms the retry succeeded -- payment now recovered"
    return "FAILURE", "simulated gateway confirms the retry failed again"
