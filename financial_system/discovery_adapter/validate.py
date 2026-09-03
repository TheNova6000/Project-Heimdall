"""
Validator: does the LLM's narrative actually hold, numerically?

Extracts money-shaped numbers from the narrative and checks each against the
set of known amounts (every retrieved fact's amount, plus 4A's own
expected/actual/unexplained figures), each within a small tolerance. A number
the narrative asserts that matches nothing in that set is a real, checkable
hallucination signal -- not a vibe, a specific figure grounded in nothing it
was actually given. This is the "Validator: does the explanation actually
hold?" layer between 4B and Controller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from financial_system.discovery_adapter.models import InvestigationResult

_MONEY_PATTERN = re.compile(r"\d[\d,]*\.\d+")  # any decimal precision -- "16.3" and "16.30" are the
                                                # same Decimal value, formatting shouldn't cause a false flag
_TOLERANCE = Decimal("0.05")


@dataclass
class ValidationReport:
    numeric_grounding_ok: bool
    grounded_amounts: list[str] = field(default_factory=list)
    ungrounded_amounts: list[str] = field(default_factory=list)
    hallucination_flags: list[str] = field(default_factory=list)


def _known_amounts(result: InvestigationResult) -> set[Decimal]:
    known: set[Decimal] = set()
    for attr in ("expected_amount", "actual_amount", "unexplained_amount"):
        v = getattr(result, attr)
        if v is not None:
            try:
                known.add(Decimal(v))
            except InvalidOperation:
                pass
    for fact in result.facts:
        for m in _MONEY_PATTERN.findall(fact):
            try:
                known.add(Decimal(m.replace(",", "")))
            except InvalidOperation:
                pass
    return known


def validate_investigation(result: InvestigationResult) -> ValidationReport:
    if not result.executed_4b or not result.narrative:
        return ValidationReport(numeric_grounding_ok=True)

    known = _known_amounts(result)
    grounded, ungrounded = [], []
    for m in _MONEY_PATTERN.findall(result.narrative):
        try:
            value = Decimal(m.replace(",", ""))
        except InvalidOperation:
            continue
        (grounded if any(abs(value - k) <= _TOLERANCE for k in known) else ungrounded).append(m)

    flags = []
    if ungrounded and result.status.value != "UNEXPLAINED":
        # An ungrounded figure in a still-UNEXPLAINED narrative is likely just
        # incidental prose (a percentage, a date fragment); one backing an
        # EXPLAINED/PARTIALLY_EXPLAINED conclusion is the actual danger case --
        # a specific wrong number driving the LLM's stated confidence.
        flags.append(f"narrative cites {ungrounded} while result is {result.status.value}, but none "
                      f"of these figures match a retrieved fact or the computed gap")

    return ValidationReport(
        numeric_grounding_ok=not ungrounded,
        grounded_amounts=grounded, ungrounded_amounts=ungrounded, hallucination_flags=flags,
    )
