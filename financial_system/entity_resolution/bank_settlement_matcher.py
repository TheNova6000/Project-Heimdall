"""
Build-order step 6: Settlement <-> BankTransaction. The one relationship NOT
given directly by the source (see DATASET_DESIGN.md) -- bank statements only
carry a UTR and free-text `description`, so this is where deterministic +
probabilistic matching actually earns its place. No LLM, no graph.

Matching logic, in order:
  1. Description-substring match: does a settlement's id-suffix appear in a
     bank transaction's description? Unambiguous hits are the strongest
     identity evidence available (this mirrors a UTR/reference lookup in real
     reconciliation) -> match_method="deterministic_description".
  2. If a description hit is claimed by more than one settlement (a suffix
     collision), amount+date corroboration breaks the tie ->
     match_method="probabilistic_disambiguated".
  3. Settlements with no description hit at all fall back to pure amount+date
     scoring over the remaining candidate pool -> match_method="probabilistic".
  4. Below PROBABILISTIC_THRESHOLD, or no candidate in the date window at all:
     unresolved. Not persisted (build-order step 9) -- an honest gap, not a
     guess.

Amount is corroborating evidence, never a hard gate: bank_adjustment and
duplicate_record cases have large, genuine amount deltas and must still match
on identity (Rules.md -- a tolerance is a matching rule, not data cleaning;
here we go further and don't even gate identity on amount, since Controller
in Phase 5 is where amount agreement gets judged, not here).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from financial_system.entity_resolution.models import EntityMatch
from financial_system.financial_state.store import FinancialStateStore

DATE_WINDOW_DAYS = 5
SUFFIX_LEN = 6
PROBABILISTIC_THRESHOLD = 0.6


def _corroboration_score(settlement_date: datetime, net_amount: Decimal,
                          bank_date: datetime, bank_amount: Decimal) -> float:
    date_diff = abs((bank_date.date() - settlement_date.date()).days)
    date_score = max(0.0, 1 - date_diff / DATE_WINDOW_DAYS)
    denom = max(float(abs(net_amount)), 1.0)
    amount_diff = abs(float(bank_amount) - float(net_amount))
    amount_score = max(0.0, 1 - amount_diff / denom)
    return round(0.5 * date_score + 0.5 * amount_score, 4)


def resolve_settlement_bank_matches(store: FinancialStateStore) -> tuple[list[EntityMatch], dict]:
    settlements = [dict(r) for r in store.all_rows("settlements")]
    bank_txns = [dict(r) for r in store.all_rows("bank_transactions")]
    for s in settlements:
        s["_date"] = datetime.fromisoformat(s["settlement_date"])
        s["_net"] = Decimal(s["net_amount"])
        s["_suffix"] = s["settlement_id"][-SUFFIX_LEN:]
    for b in bank_txns:
        b["_date"] = datetime.fromisoformat(b["value_date"])
        b["_amount"] = Decimal(b["amount"])
    by_id = {b["bank_txn_id"]: b for b in bank_txns}

    stats = dict(candidates_generated=0, deterministic=0, probabilistic=0,
                  probabilistic_disambiguated=0, unresolved=0)

    # -- pass 1: description-substring index (every settlement x every bank txn) --
    desc_claims: dict[str, list[str]] = {}  # bank_txn_id -> [settlement_id, ...]
    for s in settlements:
        window_end = s["_date"] + timedelta(days=DATE_WINDOW_DAYS)
        for b in bank_txns:
            if s["_date"] <= b["_date"] <= window_end:
                stats["candidates_generated"] += 1
                if s["_suffix"] in b["description"]:
                    desc_claims.setdefault(b["bank_txn_id"], []).append(s["settlement_id"])

    settlements_by_id = {s["settlement_id"]: s for s in settlements}
    matches: list[EntityMatch] = []
    used_bank_txns: set[str] = set()
    matched_settlements: set[str] = set()

    for bank_txn_id, claimant_ids in desc_claims.items():
        b = by_id[bank_txn_id]
        if len(claimant_ids) == 1:
            s = settlements_by_id[claimant_ids[0]]
            score = 1.0
            method = "deterministic_description"
            stats["deterministic"] += 1
        else:
            scored = [(sid, _corroboration_score(settlements_by_id[sid]["_date"],
                                                   settlements_by_id[sid]["_net"],
                                                   b["_date"], b["_amount"]))
                      for sid in claimant_ids]
            best_sid, score = max(scored, key=lambda t: t[1])
            if score < PROBABILISTIC_THRESHOLD:
                stats["unresolved"] += 1
                continue
            s = settlements_by_id[best_sid]
            method = "probabilistic_disambiguated"
            stats["probabilistic_disambiguated"] += 1

        matches.append(EntityMatch(
            subject_type="BankTransaction", subject_id=bank_txn_id,
            object_type="Settlement", object_id=s["settlement_id"], relation="deposited_as",
            match_method=method, match_score=score,
            match_evidence=[
                f"description {b['description']!r} contains settlement suffix {s['_suffix']!r}",
                f"amount+date corroboration score={score}",
            ] + ([f"disambiguated among {len(claimant_ids)} candidate settlements"]
                 if len(claimant_ids) > 1 else []),
            source_record_ids=[bank_txn_id, s["settlement_id"]],
        ))
        used_bank_txns.add(bank_txn_id)
        matched_settlements.add(s["settlement_id"])

    # -- pass 2: settlements with zero description hit -- pure amount+date fallback --
    for s in settlements:
        if s["settlement_id"] in matched_settlements:
            continue
        window_end = s["_date"] + timedelta(days=DATE_WINDOW_DAYS)
        pool = [b for b in bank_txns if b["bank_txn_id"] not in used_bank_txns
                and s["_date"] <= b["_date"] <= window_end]
        if not pool:
            stats["unresolved"] += 1
            continue
        scored = [(b, _corroboration_score(s["_date"], s["_net"], b["_date"], b["_amount"]))
                  for b in pool]
        best_b, score = max(scored, key=lambda t: t[1])
        if score < PROBABILISTIC_THRESHOLD:
            stats["unresolved"] += 1
            continue
        matches.append(EntityMatch(
            subject_type="BankTransaction", subject_id=best_b["bank_txn_id"],
            object_type="Settlement", object_id=s["settlement_id"], relation="deposited_as",
            match_method="probabilistic", match_score=score,
            match_evidence=[f"no description match; amount+date corroboration score={score}"],
            source_record_ids=[best_b["bank_txn_id"], s["settlement_id"]],
        ))
        used_bank_txns.add(best_b["bank_txn_id"])
        stats["probabilistic"] += 1

    return matches, stats
