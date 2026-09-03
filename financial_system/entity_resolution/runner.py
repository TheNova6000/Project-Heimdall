"""
Orchestrates Phase 2 in the build order from the plan:
  1. reference-key validation
  2-5. given matches (Payment<->Order/Customer/Device/Instrument, Settlement<->Payment)
  6. Settlement<->BankTransaction (deterministic + probabilistic)
  7-8. score against the held-out answer key
  9. persist only sufficiently supported matches
  10. print the report

Reads the Financial State db Phase 1 built. Zero dependency on Discovery.AI,
zero LLM calls, no graph writes -- this is still the factual substrate.

Run directly: `python -m financial_system.entity_resolution.runner`
"""
from __future__ import annotations

import sys
from pathlib import Path

from financial_system.entity_resolution.bank_settlement_matcher import resolve_settlement_bank_matches
from financial_system.entity_resolution.evaluator import score_settlement_bank_matches
from financial_system.entity_resolution.given_matches import resolve_given_matches, validate_reference_keys
from financial_system.financial_state.store import FinancialStateStore

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = REPO_ROOT / "financial_system" / "data" / "financial_state.db"


def run_phase2(db_path: Path = DB_PATH):
    if not db_path.exists():
        raise SystemExit("financial_state.db not found -- run Phase 1 first: "
                          "python -m financial_system.financial_state.builder")
    store = FinancialStateStore(db_path)

    # step 1
    violations = validate_reference_keys(store)

    # steps 2-5
    given = resolve_given_matches(store)

    # step 6
    bank_matches, match_stats = resolve_settlement_bank_matches(store)

    # steps 7-8
    score = score_settlement_bank_matches(bank_matches)

    # step 9 -- persist. given matches are 1.0-confidence by construction;
    # bank_matches already passed PROBABILISTIC_THRESHOLD inside the matcher,
    # so everything returned here already cleared the "sufficiently supported" bar.
    store.clear_entity_matches()  # idempotent re-run, not an accumulating log
    for m in given + bank_matches:
        store.add_entity_match(m.subject_type, m.subject_id, m.object_type, m.object_id,
                                m.relation, m.match_method, m.match_score,
                                m.match_evidence, m.source_record_ids)
    store.commit()

    return violations, given, bank_matches, match_stats, score


def _print_report(violations, given, bank_matches, stats, score):
    print("-- step 1: reference-key validation --")
    print(f"  violations: {len(violations)}" + ("" if not violations else f" -- {violations[:3]}"))

    print()
    print("-- steps 2-5: given matches (foreign-key relationships) --")
    by_relation = {}
    for m in given:
        by_relation[m.relation] = by_relation.get(m.relation, 0) + 1
    for relation, count in by_relation.items():
        print(f"  {relation:<16} {count}")

    print()
    print("-- step 6: Settlement <-> BankTransaction --")
    print(f"  Candidates generated        {stats['candidates_generated']}")
    print(f"  Deterministic matches        {stats['deterministic']}")
    print(f"  Probabilistic (disambig.)     {stats['probabilistic_disambiguated']}")
    print(f"  Probabilistic (no desc.)      {stats['probabilistic']}")
    print(f"  Unresolved                    {stats['unresolved']}")

    print()
    print("-- steps 7-8: evaluation against ground_truth/entity_resolution_labels.csv --")
    print(f"  Total ground-truth pairs      {score.total_ground_truth}")
    print(f"  True positives                {score.true_positives}")
    print(f"  False matches (FP)            {score.false_positives}")
    print(f"  Missed matches (FN)           {score.false_negatives}")
    print(f"  Precision                     {score.precision:.2%}")
    print(f"  Recall                        {score.recall:.2%}")
    print(f"  F1                            {score.f1:.2%}")
    if score.mismatches:
        print(f"  mismatches (first 5): {score.mismatches[:5]}")

    print()
    total_persisted = len(given) + len(bank_matches)
    print(f"-- step 9: persisted {total_persisted} EntityMatch records to entity_matches table --")

    passed = (not violations) and score.false_positives == 0 and score.recall >= 0.95
    print()
    print("PHASE 2: PASS" if passed else "PHASE 2: FAIL")
    return passed


if __name__ == "__main__":
    violations, given, bank_matches, stats, score = run_phase2()
    passed = _print_report(violations, given, bank_matches, stats, score)
    sys.exit(0 if passed else 1)
