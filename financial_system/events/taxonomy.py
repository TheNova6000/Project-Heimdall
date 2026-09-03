"""
The closed event-type taxonomy, per MIGRATION_DESIGN.md §2. Only these
values are valid `event_type`s -- enforced at write time in store.py, same
pattern as relation_types.py's own closed-vocabulary enforcement.

A correction is NOT a separate type (SettlementCorrection etc.) -- it's the
SAME event_type with `supersedes_event_id` set. event_type describes the
fact; supersedes_event_id describes the relationship between facts.
"""
from __future__ import annotations

OBSERVATIONAL = {
    "PaymentCreated", "PaymentCaptured", "PaymentFailed", "OrderCreated",
    "SettlementReceived", "BankTransactionRecorded", "RefundRecorded", "FeeRecorded",
}

REASONING = {
    "EntityMatchResolved", "VerdictProduced", "PolicyDecided",
    "InvestigationOpened", "InvestigationConcluded", "ConflictDetected", "CompoundCaseCreated",
}

ACTION = {
    "ActionRequested", "ActionExecutionStarted", "ActionOutcomeObserved",
}

EVENT_TYPES = OBSERVATIONAL | REASONING | ACTION

# Only Observational + ActionOutcomeObserved feed the Financial State
# projection (MIGRATION_DESIGN.md §6/§9) -- Reasoning events and the earlier
# Action-lifecycle events never touch world-state.
STATE_PROJECTING_TYPES = OBSERVATIONAL | {"ActionOutcomeObserved"}
