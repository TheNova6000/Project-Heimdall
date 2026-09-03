"""
InvestigationRequest/Result -- the contract between a domain agent (Controller,
later Risk/Recovery) and discovery_adapter. Pure pydantic, no Discovery.AI import
here (only investigate.py and financial_state_retriever.py touch backend.*).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class InvestigationStatus(str, Enum):
    EXPLAINED = "EXPLAINED"
    PARTIALLY_EXPLAINED = "PARTIALLY_EXPLAINED"
    UNEXPLAINED = "UNEXPLAINED"


class InvestigationRequest(BaseModel):
    subject_type: str          # "Settlement" | "Payment" (Phase 4A supports Settlement)
    subject_id: str
    question_text: str
    scope: str = "reconciliation"


class InvestigationResult(BaseModel):
    request: InvestigationRequest
    status: InvestigationStatus

    # 4A -- deterministic, computed by our own code, never by the LLM
    expected_amount: Optional[str] = None   # Decimal, stringified for JSON safety
    actual_amount: Optional[str] = None
    unexplained_amount: Optional[str] = None
    facts: list[str] = []
    evidence: list[str] = []                # entity ids referenced

    # 4B -- only populated when executed_4b is True
    executed_4b: bool = False
    ground_decision_action: Optional[str] = None   # decide_next_step's action, logged not acted on
    inferences: list[str] = []               # narrative connections Discovery.AI drew
    hypotheses: list[str] = []                # uninvestigated claims -- never promoted to facts
    investigation_confidence: Optional[float] = None
    narrative: Optional[str] = None
    resources_offered: int = 0                # full neighborhood size, before max_results truncation
    resources_used: int = 0                    # actually sent to gather_evidence

    # LLM call metrics (call_metrics.py) -- only populated when executed_4b is True
    llm_latency_seconds: Optional[float] = None
    llm_fallback_events: int = 0
    llm_full_failures: int = 0
    llm_providers_seen: list[str] = []

    execution_note: str = ""
