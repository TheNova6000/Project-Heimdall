"""
Person agent -- Phase 1 behavioral rules.

Every probability/threshold constant below states its provenance per
Rules.md #2: research-grounded (cited), a named MODELING ASSUMPTION, or
an explicit PLACEHOLDER. None of these numbers are claimed to be
empirically calibrated -- Phases.md's Phase 3 is where research-grounded
replacements would happen, each swap cited individually. Phase 1's job
is only to prove the *mechanism* (behavior driven by an agent's own
visible state) works, not to be realistic (PRD.md, Rules.md #5).

An agent's decisions here depend only on arguments passed in (its own
balance, its own income, its own risk_preference, and the RNG) -- never
on global simulation state -- matching Architecture.md's "no hidden
global state" requirement.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Income arrival
# ---------------------------------------------------------------------------

# MODELING ASSUMPTION: salaried income arrives once per month, on one fixed
# calendar day per person. Real payroll cadence varies (monthly / biweekly /
# weekly, by employer and country) -- this is a deliberate simplification
# chosen because Phase 1 needs *a* believable periodic income pattern to
# create the "balance builds up, then gets spent down" cycle the causal
# hypothesis depends on, not a validated cadence. Phase 3 candidate for a
# cited, more varied income-cadence model.
INCOME_NOISE_RANGE = (0.95, 1.05)  # MODELING ASSUMPTION: paychecks vary
# +/-5% around the nominal monthly figure (bonuses/deductions/rounding) --
# a named simplification, not a cited payroll statistic.

# ---------------------------------------------------------------------------
# Discretionary purchase decision
# ---------------------------------------------------------------------------

# MODELING ASSUMPTION: base daily probability that a person even considers
# making a discretionary purchase today, before any balance/risk adjustment.
# 0.35 => roughly one purchase attempt every ~3 days per person on average,
# a plausible order of magnitude for routine daily-life spending (food,
# transport, small purchases). Not derived from any transaction-frequency
# dataset -- Phase 3 candidate.
BASE_DAILY_SPEND_PROB = 0.35

# MODELING ASSUMPTION: risk_preference (Architecture.md's stated 0-1 Person
# trait) linearly scales spend probability between 0.7x (very cautious,
# risk_preference=0) and 1.6x (very impulsive, risk_preference=1). The
# specific multiplier range is a named, reasonable-looking choice, not an
# empirically fit elasticity -- Phase 3 candidate.
RISK_MULTIPLIER_MIN = 0.7
RISK_MULTIPLIER_MAX = 1.6

# MODELING ASSUMPTION: a person's balance relative to their own monthly
# income scales spend probability down when they are cash-strapped, but
# deliberately never to zero -- people still attempt purchases (rent,
# groceries) even when low on funds, which is exactly the situation that
# should sometimes produce a payment_failure. balance_ratio=0 (broke) ->
# 0.5x; balance_ratio>=1 (at least a full month's income banked) -> 1.0x.
# This is the specific mechanism connecting a Person's own visible state to
# their own behavior, per Architecture.md's simulation-loop requirement
# ("probability depends on balance, income_monthly, risk_preference").
BALANCE_FACTOR_MIN = 0.5
BALANCE_FACTOR_SATURATION_RATIO = 1.0  # balance_ratio at which factor hits 1.0

# MODELING ASSUMPTION: cap on daily spend probability regardless of how
# favorable balance/risk look, so no person is deterministic. Arbitrary but
# stated cap, not derived from data.
MAX_DAILY_SPEND_PROB = 0.9

# MODELING ASSUMPTION: a discretionary purchase is sized as a fraction of
# the person's own monthly income, drawn from a wide range (0.5%-12% of
# income) and then jittered multiplicatively, to get a right-skewed spread
# (many small purchases, occasional larger ones) without claiming to match
# any real merchant-spend distribution. Phase 3 candidate.
PURCHASE_FRACTION_RANGE = (0.005, 0.12)
PURCHASE_FRACTION_JITTER = (0.6, 1.6)


@dataclass
class Person:
    """Person agent. Fields match Architecture.md's Person data model exactly."""

    person_id: str
    name: str
    income_monthly: float
    balance: float  # opening balance only; Bank.Account.balance is the
    # source of truth once the simulation starts (see engine.py)
    risk_preference: float  # 0 (cautious) .. 1 (impulsive)
    payday: int  # day-of-month (1-28) salary arrives; part of this
    # agent's own state, not global -- each person has their own payday
    # so income arrivals are staggered across the population rather than
    # everyone getting paid simultaneously (MODELING ASSUMPTION: makes
    # "not everyone is paid on the 1st" explicit rather than accidental).

    # -- Rule: income arrival ------------------------------------------------
    def maybe_receive_income(self, day_of_month: int, rng: random.Random) -> float:
        """Return the salary amount received this tick, or 0.0 if not payday."""
        if day_of_month != self.payday:
            return 0.0
        noise = rng.uniform(*INCOME_NOISE_RANGE)
        return round(self.income_monthly * noise, 2)

    # -- Rule: discretionary purchase attempt --------------------------------
    def spend_probability(self, balance: float) -> float:
        """
        Probability this person attempts a purchase today, as an explicit
        function of their own balance, income, and risk_preference (see
        module-level constants above for each factor's provenance).
        """
        income = max(self.income_monthly, 1e-9)  # guard divide-by-zero;
        # income_monthly=0 is not a realistic input but must not crash.
        balance_ratio = max(0.0, balance / income)
        balance_factor = BALANCE_FACTOR_MIN + (1.0 - BALANCE_FACTOR_MIN) * min(
            1.0, balance_ratio / BALANCE_FACTOR_SATURATION_RATIO
        )
        risk_factor = RISK_MULTIPLIER_MIN + (
            RISK_MULTIPLIER_MAX - RISK_MULTIPLIER_MIN
        ) * self.risk_preference
        prob = BASE_DAILY_SPEND_PROB * balance_factor * risk_factor
        return min(MAX_DAILY_SPEND_PROB, prob)

    def wants_to_spend(self, balance: float, rng: random.Random) -> bool:
        return rng.random() < self.spend_probability(balance)

    def purchase_amount(self, rng: random.Random) -> float:
        lo, hi = PURCHASE_FRACTION_RANGE
        jlo, jhi = PURCHASE_FRACTION_JITTER
        fraction = rng.uniform(lo, hi) * rng.uniform(jlo, jhi)
        return round(self.income_monthly * fraction, 2)
