"""
Merchant agent -- Phase 1 scope: a sales recipient with one bank account.
Architecture.md scopes Merchant to "sales, basic ledger" only. Merchants
have no spending or settlement behavior of their own in Phase 1 -- basic
settlement between Merchant and Bank is explicit Phase 2 scope
(Phases.md, Phase 2), so a Merchant here purely accumulates balance from
Person purchases via its Bank account.
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
    bank_account_id: str
    category: str = "general"
