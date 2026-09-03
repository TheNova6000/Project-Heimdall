"""
Adversarial test for accounting_consistency.py's two invariants, per
FINANCIAL_ACCOUNTING_BOUNDARY_REVIEW.md's B-lite recommendation. Runs the
real check against the full 610-settlement corpus (cross-tabulated
against reconciliation_labels.csv's own root_cause taxonomy) plus
targeted synthetic fixtures for the two scenarios the real corpus never
happens to exercise on its own (a bare payment-sum mismatch, and both
exceptions firing together) -- named honestly as synthetic, not
presented as corpus evidence.

Run directly: `python -m financial_system.reconciliation.accounting_consistency_test`
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from financial_system.financial_state.builder import build_financial_state
from financial_system.financial_state.models import Payment, Provenance, Settlement, SettlementPayment
from financial_system.financial_state.store import FinancialStateStore
from financial_system.reconciliation.accounting_consistency import (
    NET_AMOUNT_MISMATCH, PAYMENT_SUM_MISMATCH, check_accounting_consistency,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GT_PATH = REPO_ROOT / "financial_system" / "data" / "ground_truth" / "reconciliation_labels.csv"
DATA_DIR = REPO_ROOT / "financial_system" / "data"


def _fresh(path: Path) -> None:
    if path.exists():
        path.unlink()


def test_full_corpus_breakdown() -> bool:
    print("-- 1. Full 610-settlement corpus, cross-tabulated against ground-truth root_cause --")
    # A dedicated db path, not the shared financial_state.db every other
    # phase's runner reads: build_financial_state() only rebuilds Phase-1
    # tables, not Phase-2's entity_matches, so calling it against the
    # shared default here would silently wipe entity_matches for every
    # other script (found and fixed during the Recovery expected-value
    # work's regression sweep -- Risk's recall went 96.3% -> 0% from this
    # exact call before the fix).
    _fresh(DATA_DIR / "state_ac_corpus.db")
    state, _ = build_financial_state(db_path=DATA_DIR / "state_ac_corpus.db")
    labels = {}
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["settlement_id"]] = row["root_cause"]

    settlement_ids = [dict(r)["settlement_id"] for r in state.all_rows("settlements")]
    by_cause: dict[str, Counter] = defaultdict(Counter)
    net_count = pay_count = pass_count = 0
    for sid in settlement_ids:
        result = check_accounting_consistency(state, sid)
        rc = labels.get(sid, "?")
        key = "PASS" if result.status == "PASS" else "|".join(sorted(result.exceptions))
        by_cause[rc][key] += 1
        if NET_AMOUNT_MISMATCH in result.exceptions:
            net_count += 1
        if PAYMENT_SUM_MISMATCH in result.exceptions:
            pay_count += 1
        if result.status == "PASS":
            pass_count += 1

    print(f"  {len(settlement_ids)} real settlements checked")
    for rc in sorted(by_cause):
        print(f"    {rc:<20} {dict(by_cause[rc])}")
    print(f"  PASS: {pass_count}, NET_AMOUNT_MISMATCH: {net_count}, PAYMENT_SUM_MISMATCH: {pay_count}")
    print("  (PAYMENT_SUM_MISMATCH is 0 across the real corpus once duplicate settlement_payments lines")
    print("   are correctly deduplicated -- corrects this checkpoint's own earlier, non-deduplicated")
    print("   '19/610' figure from FINANCIAL_ACCOUNTING_BOUNDARY_REVIEW.md's grounding section, which")
    print("   turns out to have been entirely an artifact of the already-known duplicate_record cases,")
    print("   not a second, independent inconsistency)")
    ok = net_count == 77 and pay_count == 0 and pass_count == 533
    print("PASS" if ok else "FAIL")
    return ok, state


def test_valid_settlement_both_pass(state: FinancialStateStore) -> bool:
    print("\n-- 2. A real, clean settlement -- both invariants pass --")
    labels = {}
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["settlement_id"]] = row["root_cause"]
    clean_sid = next(sid for sid, rc in labels.items() if rc == "none"
                      and check_accounting_consistency(state, sid).status == "PASS")
    result = check_accounting_consistency(state, clean_sid)
    ok = result.status == "PASS" and not result.exceptions
    print(f"  {clean_sid}: status={result.status}, exceptions={result.exceptions}")
    print("PASS" if ok else "FAIL")
    return ok


def test_net_amount_mismatch_alone(state: FinancialStateStore) -> bool:
    print("\n-- 3. gross/fee/tax/net mismatch -> exactly one finding, not two --")
    settlement_ids = [dict(r)["settlement_id"] for r in state.all_rows("settlements")]
    sid = next(sid for sid in settlement_ids
               if check_accounting_consistency(state, sid).exceptions == [NET_AMOUNT_MISMATCH])
    result = check_accounting_consistency(state, sid)
    ok = result.exceptions == [NET_AMOUNT_MISMATCH]
    print(f"  {sid}: gross={result.gross_amount} fee={result.fee_amount} tax={result.tax_amount} "
          f"net={result.net_amount} computed_net={result.computed_net} diff={result.net_amount_difference}")
    print(f"  exceptions: {result.exceptions}")
    print("PASS" if ok else "FAIL")
    return ok


def test_duplicate_lines_not_double_counted(state: FinancialStateStore) -> bool:
    print("\n-- 4. Duplicate settlement_payments lines don't cause a false PAYMENT_SUM_MISMATCH --")
    labels = {}
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["settlement_id"]] = row["root_cause"]
    dup_sid = next(sid for sid, rc in labels.items() if rc == "duplicate_record")
    result = check_accounting_consistency(state, dup_sid)
    ok = PAYMENT_SUM_MISMATCH not in result.exceptions and len(result.duplicate_payment_ids) >= 1
    print(f"  {dup_sid}: duplicate_payment_ids={result.duplicate_payment_ids}")
    print(f"  gross={result.gross_amount} payment_sum(distinct)={result.payment_sum} "
          f"diff={result.payment_sum_difference}")
    print(f"  PAYMENT_SUM_MISMATCH correctly absent: {PAYMENT_SUM_MISMATCH not in result.exceptions}")
    print("PASS" if ok else "FAIL")
    return ok


def test_split_settlement_does_not_misfire(state: FinancialStateStore) -> bool:
    """The user's explicit concern: don't assume payment-sum == gross unless
    domain semantics say so. Checked empirically against every real
    split_settlement-labeled case, rather than assumed either way."""
    print("\n-- 5. split_settlement cases -- does the payment-sum invariant misfire on legitimate splits? --")
    labels = {}
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["settlement_id"]] = row["root_cause"]
    split_sids = [sid for sid, rc in labels.items() if rc == "split_settlement"]
    misfires = [sid for sid in split_sids
                if PAYMENT_SUM_MISMATCH in check_accounting_consistency(state, sid).exceptions]
    print(f"  {len(split_sids)} split_settlement-labeled settlements checked")
    print(f"  PAYMENT_SUM_MISMATCH fired on: {len(misfires)} of them")
    print("  (empirically zero in this dataset -- this dataset's split_settlement construction does not")
    print("   split a payment's value across settlement boundaries at the settlement_payments linkage")
    print("   level, so the whole-payment-per-settlement assumption happens to hold here. This is a")
    print("   property OF THIS DATASET, not a guarantee the check itself makes -- SettlementPayment has")
    print("   no amount field (FINANCIAL_ACCOUNTING_BOUNDARY_REVIEW.md Q6/Q12), so a dataset that DID")
    print("   split a payment's value across settlements would misfire this check, honestly, since the")
    print("   model has no way to represent a partial linkage)")
    ok = len(misfires) == 0
    print("PASS" if ok else "FAIL")
    return ok


def _synthetic_state(path: Path, gross, fee, tax, net, payment_amount) -> FinancialStateStore:
    _fresh(path)
    state = FinancialStateStore(path)
    prov = Provenance(source_file="synthetic", source_record_id="synthetic", row_number=1,
                       ingestion_run_id="synthetic", ingested_at="2026-01-01T00:00:00")
    from datetime import datetime
    state.add_payment(Payment(
        payment_id="pay_synth", order_id="ord_synth", customer_id="cust_synth", merchant_id="merch_synth",
        device_id="dev_synth", instrument_id="instr_synth", amount=Decimal(payment_amount), currency="INR",
        status="success", created_at=datetime(2026, 1, 1), captured_at=datetime(2026, 1, 1), provenance=prov,
    ))
    state.add_settlement(Settlement(
        settlement_id="sett_synth", merchant_id="merch_synth", settlement_date=datetime(2026, 1, 2),
        gross_amount=Decimal(gross), fee_amount=Decimal(fee), tax_amount=Decimal(tax),
        net_amount=Decimal(net), provenance=prov,
    ))
    state.add_settlement_payment(SettlementPayment(
        settlement_id="sett_synth", payment_id="pay_synth", provenance=prov,
    ))
    state.commit()
    return state


def test_synthetic_payment_sum_mismatch_alone() -> bool:
    print("\n-- 6. Synthetic: a bare PAYMENT_SUM_MISMATCH, net amount otherwise consistent --")
    # gross=1000, fee=50, tax=10 -> computed_net=940=net (consistent); but the
    # only linked payment is only worth 500 -- gross doesn't match what's linked.
    state = _synthetic_state(DATA_DIR / "state_ac_synth1.db", gross=1000, fee=50, tax=10, net=940,
                              payment_amount=500)
    result = check_accounting_consistency(state, "sett_synth")
    state.close()
    ok = result.exceptions == [PAYMENT_SUM_MISMATCH]
    print(f"  gross=1000 fee=50 tax=10 net=940 (internally consistent), linked payment=500")
    print(f"  exceptions: {result.exceptions}")
    print("PASS" if ok else "FAIL")
    return ok


def test_synthetic_both_mismatch() -> bool:
    print("\n-- 7. Synthetic: both invariants violated simultaneously -> two independent findings --")
    # gross=1000, fee=50, tax=10 -> computed_net=940, but net=800 (mismatch);
    # AND linked payment is only 500 (mismatch too).
    state = _synthetic_state(DATA_DIR / "state_ac_synth2.db", gross=1000, fee=50, tax=10, net=800,
                              payment_amount=500)
    result = check_accounting_consistency(state, "sett_synth")
    state.close()
    ok = sorted(result.exceptions) == sorted([NET_AMOUNT_MISMATCH, PAYMENT_SUM_MISMATCH])
    print(f"  gross=1000 fee=50 tax=10 net=800 (computed_net=940, mismatch), linked payment=500 (mismatch)")
    print(f"  exceptions: {sorted(result.exceptions)}")
    print("PASS" if ok else "FAIL")
    return ok


def test_settlement_not_found(state: FinancialStateStore) -> bool:
    print("\n-- 8. missing_settlement -- settlement_id genuinely absent from state --")
    labels = {}
    with open(GT_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["settlement_id"]] = row["root_cause"]
    missing_sid = next(sid for sid, rc in labels.items() if rc == "missing_settlement")
    result = check_accounting_consistency(state, missing_sid)
    ok = result.status == "EXCEPTION" and result.exceptions == ["SETTLEMENT_NOT_FOUND"]
    print(f"  {missing_sid}: status={result.status}, exceptions={result.exceptions}, note={result.note!r}")
    print("PASS" if ok else "FAIL")
    return ok


def run() -> bool:
    ok1, state = test_full_corpus_breakdown()
    results = {
        "full_corpus_breakdown": ok1,
        "valid_settlement_both_pass": test_valid_settlement_both_pass(state),
        "net_amount_mismatch_alone": test_net_amount_mismatch_alone(state),
        "duplicate_lines_not_double_counted": test_duplicate_lines_not_double_counted(state),
        "split_settlement_does_not_misfire": test_split_settlement_does_not_misfire(state),
        "synthetic_payment_sum_mismatch_alone": test_synthetic_payment_sum_mismatch_alone(),
        "synthetic_both_mismatch": test_synthetic_both_mismatch(),
        "settlement_not_found": test_settlement_not_found(state),
    }
    print("\n== summary ==")
    for name, ok in results.items():
        print(f"  {name}: {'PASS' if ok else 'FAIL'}")
    passed = all(results.values())
    print(f"\nACCOUNTING CONSISTENCY ADVERSARIAL TEST: {'PASS' if passed else 'FAIL'}")
    return passed


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(0 if run() else 1)
