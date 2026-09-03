"""
Event -- the append-only temporal primitive, per MIGRATION_DESIGN.md §1.
Never updated after insertion (enforced in store.py, not just by convention).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class Event(BaseModel):
    event_id: str
    event_type: str                     # from taxonomy.EVENT_TYPES -- closed set
    schema_version: int = 1
    subject_id: str
    source: str
    source_event_id: Optional[str] = None   # external dedup key (§4)
    occurred_at: datetime
    recorded_at: datetime
    payload: dict[str, Any] = {}
    correlation_id: str                  # the case (§1a) -- == case_id for this migration
    causation_id: Optional[str] = None    # the specific prior event that produced this one
    supersedes_event_id: Optional[str] = None   # set only on a correction (§3)
