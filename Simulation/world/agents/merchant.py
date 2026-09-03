"""
Merchant agent -- a sales recipient with a bank account.
Architecture.md scopes Merchant to "sales, basic ledger" only; Merchants
still have no spending behavior of their own (that stays out of scope --
see Memory.md).

Phase 2 change (Phases.md, Phase 2 -- "basic settlement between Merchant
and Bank"): a Merchant now has TWO accounts rather than one --
`bank_account_id` (settled/spendable funds) and `pending_account_id`
(funds received from a purchase but not yet settled/available). Purchase
proceeds land in the pending account first; `world/engine.py`'s daily
settlement sweep moves them into the settled account the next simulated
day (T+1 -- see engine.py for the provenance of that timing rule). This
is the specific "received vs. settled" mechanism Phase 2 exists to add,
rather than purchase money being instantly usable, per this task's
brief.
"""

from __future__ import annotations

from dataclasses import dataclass

# PLACEHOLDER: category is a cosmetic label only (does not affect any
# probability or behavior in Phase 1) used purely so stats/report.py and
# the output CSVs have something more legible than an opaque merchant_id
# to group by. Not research-grounded, not claimed to reflect any real
# merchant-category mix -- swap or extend freely.
MERCHANT_CATEGORIES = ("groceries", "transport", "utilities", "retail", "dining")


@dataclass
class Merchant:
    merchant_id: str
    name: str
    bank_account_id: str  # settled/spendable funds -- source of truth for
    # merchants.csv's "balance" column, same convention as Phase 1
    category: str = "general"
    pending_account_id: str = ""  # Phase 2: holds proceeds received but
    # not yet settled; "" only as a dataclass-default placeholder, always
    # set to a real account_id by SimulationEngine._build_world
