"""
EntityMatch is the one shape every resolved relationship takes, whether it was
trivially given (a foreign key already present in the source) or genuinely
resolved (Settlement <-> BankTransaction). Same contract either way, so Phase 3
can write every one of them into the graph uniformly as a `matches` edge.

No LLM anywhere in this package -- match_method is always one of the values
below, never "llm".
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

MatchMethod = Literal[
    "foreign_key",                 # given directly by the source (steps 2-5)
    "deterministic_description",   # unambiguous description-substring match
    "probabilistic",               # amount+date scoring, no description evidence
    "probabilistic_disambiguated", # description matched >1 candidate; amount+date broke the tie
]


class EntityMatch(BaseModel):
    subject_type: str          # e.g. "Payment"
    subject_id: str
    object_type: str           # e.g. "Settlement"
    object_id: str
    relation: str               # e.g. "belongs_to", "settles_into" -- see ARCHITECTURE.md relation table
    match_method: MatchMethod
    match_score: float          # 0..1
    match_evidence: list[str]
    source_record_ids: list[str]  # every raw record this match rests on
