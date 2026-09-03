"""Build-order steps 7-8: score the Settlement<->BankTransaction matches
against the held-out answer key. This file only reads
data/ground_truth/entity_resolution_labels.csv -- nothing in
bank_settlement_matcher.py reads it (Rules.md: an agent that reads its own
answer key is cheating on its own eval)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from financial_system.entity_resolution.models import EntityMatch

GT_DIR = Path(__file__).resolve().parent.parent / "data" / "ground_truth"


@dataclass
class ResolutionScore:
    total_ground_truth: int
    true_positives: int
    false_positives: int
    false_negatives: int  # ground truth pairs we left unresolved or matched wrong
    precision: float
    recall: float
    f1: float
    mismatches: list[str]


def load_answer_key() -> dict[str, str]:
    """bank_txn_id -> true settlement_id"""
    answer = {}
    with open(GT_DIR / "entity_resolution_labels.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            answer[row["bank_txn_id"]] = row["settlement_id"]
    return answer


def score_settlement_bank_matches(matches: list[EntityMatch]) -> ResolutionScore:
    answer = load_answer_key()
    predicted = {m.subject_id: m.object_id for m in matches
                 if m.subject_type == "BankTransaction" and m.object_type == "Settlement"}

    tp = fp = 0
    mismatches = []
    for bank_txn_id, true_settlement_id in answer.items():
        if bank_txn_id not in predicted:
            continue  # counted as a false negative below (unresolved)
        if predicted[bank_txn_id] == true_settlement_id:
            tp += 1
        else:
            fp += 1
            mismatches.append(
                f"{bank_txn_id}: predicted {predicted[bank_txn_id]!r}, true {true_settlement_id!r}")

    resolved_but_not_in_answer = [b for b in predicted if b not in answer]
    fp += len(resolved_but_not_in_answer)
    for b in resolved_but_not_in_answer:
        mismatches.append(f"{b}: matched to {predicted[b]!r}, not in answer key at all")

    fn = len(answer) - tp  # every ground-truth pair we didn't get exactly right
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / len(answer) if answer else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return ResolutionScore(
        total_ground_truth=len(answer), true_positives=tp, false_positives=fp,
        false_negatives=fn, precision=round(precision, 4), recall=round(recall, 4),
        f1=round(f1, 4), mismatches=mismatches,
    )
