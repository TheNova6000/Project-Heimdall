"""
Expected-value Recovery decisioning -- a second, deliberately separate layer
on top of Recovery's own category-level proposal (recovery_agent.py), not a
replacement for it. Recovery's decision/decision_score stay exactly what
they are today: category-level, honest, "never a per-instance guess" (per
recovery_agent.py's own docstring). This module answers a narrower,
different question: given the SAME category-level success rate Recovery
already reports, is retrying THIS specific payment worth it once its real
economics and real cross-domain risk are priced in?

Every constant below is earned from this dataset, not invented -- see the
docstring on each one for exactly how it was measured, including the sample
size, so nobody downstream mistakes a 10-device calibration for a
population-scale one.

    P(success) -- category base rate (recovery/signals.py FAILURE_TAXONOMY)
                   -- CANNOT be improved per-payment: confirmed by reading
                      data_generator/generate_dataset.py:224 --
                      `retry_success = random.random() < spec["retry_success_p"]`
                      is a pure Bernoulli draw from the category rate with
                      ZERO dependence on amount, customer, device, or
                      timing. Any per-payment P(success) model trained on
                      this dataset would be fitting noise, not signal. This
                      is a fact about how the data was generated, not a
                      modeling shortfall -- stated here rather than
                      discovered later.
    value        -- payments.csv's own `amount` field. Real, per-payment.
    fee cost     -- fees.csv's own gateway fee, empirically an exact flat
                     2.00% of amount across all 840 real fee rows (mean =
                     median = min = max = 0.0200 -- not an average masking
                     variance, a literal fixed rate in this dataset).
    fraud harm   -- P(fraud | device risk tier) x value. The probability is
                     an EMPIRICAL rate measured against risk_labels.csv's
                     real is_fraud ground truth, joined across every
                     multi-sharer device in the full graph (not the 43-case
                     curated Phase 6 test set) -- see RISK_HARM_RATE_BY_TIER
                     below for the exact counts and the smoothing applied.
                     The magnitude (harm ~= value) follows the standard
                     card-fraud-economics convention that chargeback
                     exposure on a fraudulent transaction is bounded by the
                     transaction amount itself -- not a separately invented
                     multiplier.
"""
from __future__ import annotations

from dataclasses import dataclass

from financial_system.financial_graph.repository import GraphRepository
from financial_system.recovery.signals import RecoverySignals, compute_recovery_signals
from financial_system.risk.scoring import risk_tier, score_signals
from financial_system.risk.signals import compute_device_risk_signals

EV_LOGIC_VERSION = "recovery-ev-v1"

# fees.csv: n=840 successful payments, fee_amount/amount is EXACTLY 0.0200
# for every single row (mean=median=min=max=0.0200) -- not fit, read off
# the generator's own fixed schedule.
FEE_RATE = 0.02

# Empirical P(>=1 fraud-ring sharer | device risk tier), measured across
# EVERY multi-sharer device in the full graph (10 devices total -- this
# dataset's fraud population is small, and that smallness is reported
# honestly rather than hidden behind a smoothed number that looks more
# confident than 10 data points support):
#   LOW:    4 devices, 0 with a fraud-ring sharer  -- raw rate 0.000
#   MEDIUM: 0 devices                              -- no examples at all
#   HIGH:   6 devices, 6 with a fraud-ring sharer  -- raw rate 1.000
# Raw 0/1 rates from n=4/n=6 samples would overclaim certainty a handful of
# devices can't support, so each is Laplace (add-one) smoothed:
#   LOW:    (0+1)/(4+2) = 0.167
#   HIGH:   (6+1)/(6+2) = 0.875
# MEDIUM has zero devices in this corpus at any theshold split tried -- no
# empirical rate exists to smooth. Linearly interpolated between the
# smoothed LOW and HIGH rates as an explicit, stated assumption (monotonic
# in risk tier by construction), never claimed as measured.
RISK_HARM_RATE_BY_TIER = {
    "NONE": 0.0,     # fewer than 2 sharers -- Risk does not even score this device
    "LOW": 1 / 6,
    "MEDIUM": (1 / 6 + 7 / 8) / 2,
    "HIGH": 7 / 8,
}


@dataclass
class ExpectedValueResult:
    payment_id: str
    value: float
    base_success_rate: float          # Recovery's own category rate, unchanged
    fee_cost: float
    risk_tier: str                    # NONE / LOW / MEDIUM / HIGH
    harm_rate: float
    harm_cost: float
    expected_value: float
    category_recommendation: str      # what Recovery alone would say: RETRY / DO_NOT_RETRY / ESCALATE
    ev_recommendation: str            # RETRY / DO_NOT_RETRY
    diverges: bool                    # True iff category_recommendation and ev_recommendation disagree
    evidence: list[str]


def _device_risk_tier(graph: GraphRepository, payment_id: str) -> str:
    device_edges = graph.edges_from(payment_id, "used_device")
    if not device_edges:
        return "NONE"
    device_id = device_edges[0].object_id
    sharers = graph.edges_to(device_id, "uses")
    if len(sharers) < 2:
        return "NONE"
    signals = compute_device_risk_signals(graph, device_id)
    score, _ = score_signals(signals)
    return risk_tier(score)


def compute_expected_value(graph: GraphRepository, payment_id: str,
                            signals: RecoverySignals | None = None) -> ExpectedValueResult | None:
    """None if this payment isn't a case Recovery would even consider retrying
    (not failed, no known category, or a non-recoverable category) -- EV only
    has something to say about payments where the category-level answer is
    already RETRY; everywhere else Recovery's existing logic is untouched and
    this module has nothing to add."""
    if signals is None:
        signals = compute_recovery_signals(graph, payment_id)

    if signals.status != "failed" or not signals.known_category or not signals.is_recoverable_category:
        return None
    if signals.has_alternate_success:
        return None  # already an absolute DO_NOT_RETRY for duplicate-charge safety -- EV has nothing to add

    payment = graph.get_node(payment_id)
    value = float(payment.properties.get("amount", 0.0)) if payment else 0.0

    tier = _device_risk_tier(graph, payment_id)
    harm_rate = RISK_HARM_RATE_BY_TIER[tier]

    fee_cost = FEE_RATE * value
    harm_cost = harm_rate * value
    expected_value = signals.base_success_rate * value - fee_cost - harm_cost

    ev_recommendation = "RETRY" if expected_value > 0 else "DO_NOT_RETRY"
    category_recommendation = "RETRY"  # signals.is_recoverable_category already checked True above

    return ExpectedValueResult(
        payment_id=payment_id, value=value, base_success_rate=signals.base_success_rate,
        fee_cost=fee_cost, risk_tier=tier, harm_rate=harm_rate, harm_cost=harm_cost,
        expected_value=expected_value, category_recommendation=category_recommendation,
        ev_recommendation=ev_recommendation, diverges=(ev_recommendation != category_recommendation),
        evidence=list(signals.evidence),
    )
