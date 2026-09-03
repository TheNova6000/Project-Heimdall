"""
Serializes one complete investigation case (4A + 4B + LLM call metrics +
numeric-grounding validation) to the schema this project reports against, and
appends it to a JSONL file as each case completes -- streaming, so a run that
gets interrupted mid-batch (rate limits made this a real risk in the 40-case
run) still leaves every case investigated so far on disk, not just a one-line
console summary.

This turns a batch run from "the model got X% correct" into "here is exactly
why every decision was made" -- Rules.md's own principle (never report a
metric that wasn't actually computed) applied to our own tooling, not just to
the numbers we report.
"""
from __future__ import annotations

import json
from pathlib import Path

from financial_system.discovery_adapter.models import InvestigationResult
from financial_system.discovery_adapter.validate import validate_investigation


def build_case_record(settlement_id: str, root_cause: str, ground_truth_is_explainable: bool,
                       result: InvestigationResult) -> dict:
    validation = validate_investigation(result)
    correct = (result.status.value == "EXPLAINED") == ground_truth_is_explainable
    return {
        "case_id": settlement_id,
        "root_cause": root_cause,
        "settlement_id": settlement_id,
        "ground_truth_is_explainable": ground_truth_is_explainable,
        "correct": correct,
        "4A": {
            "status": result.status.value,
            "expected_amount": result.expected_amount,
            "actual_amount": result.actual_amount,
            "unexplained_amount": result.unexplained_amount,
            "deterministic_evidence": result.facts,
        },
        "4B": {
            "executed": result.executed_4b,
            "ground_decision_action": result.ground_decision_action,
            "confidence": result.investigation_confidence,
            "narrative": result.narrative,
            "hypotheses": result.hypotheses,
            "evidence": result.evidence,
            "resources_offered": result.resources_offered,
            "resources_used": result.resources_used,
        },
        "llm": {
            "providers_seen": result.llm_providers_seen,
            "latency_seconds": result.llm_latency_seconds,
            "fallback_events": result.llm_fallback_events,
            "full_failures": result.llm_full_failures,
        },
        "validation": {
            "numeric_grounding_ok": validation.numeric_grounding_ok,
            "grounded_amounts": validation.grounded_amounts,
            "ungrounded_amounts": validation.ungrounded_amounts,
            "hallucination_flags": validation.hallucination_flags,
        },
        "execution_note": result.execution_note,
    }


def append_case_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def load_case_records(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
