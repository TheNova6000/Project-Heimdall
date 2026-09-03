"""
Synthetic financial universe generator.

Produces data/raw/ (what ingestion agents read) and data/ground_truth/ (held out,
scoring + demo only). See data/DATASET_DESIGN.md for the design rationale.

Usage: python generate_dataset.py
"""
import csv
import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

SEED = 42
random.seed(SEED)

ROOT = Path(__file__).resolve().parent.parent / "data"
RAW = ROOT / "raw"
GT = ROOT / "ground_truth"

NOW = datetime(2026, 9, 2, 12, 0, 0)
WINDOW_DAYS = 60
START = NOW - timedelta(days=WINDOW_DAYS)

N_MERCHANTS = 25
N_CUSTOMERS = 400
N_PAYMENTS = 1000
FAIL_RATE = 0.15
REFUND_RATE = 0.10  # of successful payments

FIRST_NAMES = ["Aarav", "Vivaan", "Aditi", "Diya", "Kabir", "Ishaan", "Meera", "Riya",
               "Arjun", "Ananya", "Rohan", "Sana", "Kunal", "Priya", "Neha", "Zoya",
               "Karan", "Tara", "Yash", "Simran"]
LAST_NAMES = ["Sharma", "Verma", "Iyer", "Reddy", "Nair", "Khan", "Gupta", "Rao",
              "Mehta", "Joshi", "Kapoor", "Bose", "Chatterjee", "Pillai", "Menon"]
MERCHANT_NAMES = ["Kirana Express", "Urban Threads", "PixelCraft Studio", "GreenLeaf Organics",
                   "SwiftCart", "BrewHouse Coffee", "FitZone Gym", "PageTurner Books",
                   "TechNest Gadgets", "Sunrise Bakery", "MetroCabs", "CloudDesk SaaS",
                   "PetPals Store", "Artisan Wood Co", "Zenith Fitness", "QuickFix Repairs",
                   "Bloom Florist", "NightOwl Cinema", "TrailBlazer Outdoors", "PureGlow Skincare",
                   "CampusEats", "VoltCharge EV", "Wanderlust Travels", "CraftBrew Taproom",
                   "NimbusCloud Hosting"]

FAILURE_REASONS = {
    "technical_failure": dict(is_recoverable=True, retry_success_p=0.85, action="RETRY_PAYMENT"),
    "timeout": dict(is_recoverable=True, retry_success_p=0.80, action="RETRY_PAYMENT"),
    "insufficient_funds": dict(is_recoverable=True, retry_success_p=0.45, action="RETRY_LATER"),
    "authentication_failure": dict(is_recoverable=True, retry_success_p=0.55, action="RETRY_ALT_METHOD"),
    "issuer_declined": dict(is_recoverable=True, retry_success_p=0.20, action="RETRY_ALT_METHOD"),
    "risk_block": dict(is_recoverable=False, retry_success_p=0.0, action="MANUAL_REVIEW"),
    "expired": dict(is_recoverable=False, retry_success_p=0.0, action="REQUEST_CUSTOMER_ACTION"),
}
FAILURE_WEIGHTS = [0.22, 0.18, 0.20, 0.15, 0.15, 0.05, 0.05]

RECON_CASES = ["timing_skew", "partial_refund", "duplicate_record", "missing_settlement",
               "split_settlement", "fee_discrepancy", "bank_adjustment", "currency_conversion"]


def rid(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def rand_dt(start=START, end=NOW):
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def rand_amount():
    tier = random.choices(["small", "medium", "large"], weights=[0.55, 0.35, 0.10])[0]
    if tier == "small":
        return round(random.uniform(100, 1500), 2)
    if tier == "medium":
        return round(random.uniform(1500, 12000), 2)
    return round(random.uniform(12000, 50000), 2)


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def gen_merchants():
    rows = []
    for i, name in enumerate(MERCHANT_NAMES[:N_MERCHANTS]):
        rows.append(dict(
            merchant_id=f"merch_{i+1:03d}",
            name=name,
            category=random.choice(["retail", "food", "services", "saas", "travel", "fitness"]),
            created_at=iso(rand_dt(NOW - timedelta(days=900), NOW - timedelta(days=200))),
        ))
    return rows


def gen_customers():
    rows = []
    for i in range(N_CUSTOMERS):
        rows.append(dict(
            customer_id=f"cust_{i+1:04d}",
            name=f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
            email=f"user{i+1:04d}@example.com",
            created_at=iso(rand_dt(NOW - timedelta(days=700), NOW - timedelta(days=1))),
        ))
    return rows


def gen_devices_and_rings(customers):
    """Assigns each customer a primary device. Carves out fraud rings and benign
    shared-device pairs on top of that base assignment. Returns (devices, customer_device,
    risk_labels)."""
    devices = []
    customer_device = {}
    risk_labels = {}

    for i, c in enumerate(customers):
        did = f"dev_{i+1:04d}"
        devices.append(dict(
            device_id=did,
            fingerprint=uuid.uuid4().hex[:16],
            first_seen_at=c["created_at"],
        ))
        customer_device[c["customer_id"]] = did
        risk_labels[c["customer_id"]] = dict(is_fraud=False, ring_id="", pattern="none")

    cust_ids = [c["customer_id"] for c in customers]
    used = set()

    # 6 fraud rings, 3-5 members each, sharing one device
    for ring_no in range(1, 7):
        size = random.randint(3, 5)
        pool = [cid for cid in cust_ids if cid not in used]
        members = random.sample(pool, size)
        used.update(members)
        shared_device = customer_device[members[0]]
        ring_id = f"ring_{ring_no:02d}"
        for m in members:
            customer_device[m] = shared_device
            risk_labels[m] = dict(is_fraud=True, ring_id=ring_id, pattern="fraud_ring")

    # 8 benign shared-device pairs (e.g. family), older accounts, no fraud label
    for pair_no in range(1, 9):
        pool = [cid for cid in cust_ids if cid not in used]
        pair = random.sample(pool, 2)
        used.update(pair)
        shared_device = customer_device[pair[0]]
        for m in pair:
            customer_device[m] = shared_device
            risk_labels[m] = dict(is_fraud=False, ring_id="", pattern="benign_shared_device")

    used_device_ids = set(customer_device.values())
    devices = [d for d in devices if d["device_id"] in used_device_ids]
    return devices, customer_device, risk_labels


def gen_instruments(customers):
    rows = []
    cust_instruments = {}
    types = ["card", "upi", "netbanking"]
    for c in customers:
        n = random.choices([1, 2], weights=[0.7, 0.3])[0]
        ids = []
        for _ in range(n):
            iid = rid("instr")
            rows.append(dict(
                instrument_id=iid,
                type=random.choice(types),
                masked_identifier="XXXX" + str(random.randint(1000, 9999)),
                customer_id=c["customer_id"],
            ))
            ids.append(iid)
        cust_instruments[c["customer_id"]] = ids
    return rows, cust_instruments


def gen_payments(merchants, customers, customer_device, cust_instruments, risk_labels):
    orders, payments, recovery_rows = [], [], []
    merchant_ids = [m["merchant_id"] for m in merchants]

    ring_members = [cid for cid, v in risk_labels.items() if v["pattern"] == "fraud_ring"]
    ring_by_id = {}
    for cid in ring_members:
        ring_by_id.setdefault(risk_labels[cid]["ring_id"], []).append(cid)

    remaining = N_PAYMENTS

    # Ring bursts: each ring gets a short-window velocity burst of clustered amounts.
    for ring_id, members in ring_by_id.items():
        burst_n = random.randint(6, 10)
        burst_start = rand_dt(NOW - timedelta(days=30), NOW - timedelta(days=1))
        base_amount = rand_amount()
        merchant_id = random.choice(merchant_ids)
        for _ in range(burst_n):
            cid = random.choice(members)
            amount = round(base_amount * random.uniform(0.92, 1.08), 2)
            ts = burst_start + timedelta(minutes=random.randint(0, 45))
            _make_payment(orders, payments, merchant_id, cid, amount, ts,
                          customer_device, cust_instruments,
                          force_success_p=0.75)
            remaining -= 1

    # Rest: normal traffic across all customers (including ring/benign members doing
    # unrelated ordinary purchases elsewhere, and everyone else).
    all_cust_ids = [c for c in customer_device.keys()]
    for _ in range(max(remaining, 0)):
        cid = random.choice(all_cust_ids)
        merchant_id = random.choice(merchant_ids)
        amount = rand_amount()
        ts = rand_dt()
        _make_payment(orders, payments, merchant_id, cid, amount, ts,
                       customer_device, cust_instruments, force_success_p=None)

    for p in payments:
        if p["status"] == "failed":
            spec = FAILURE_REASONS[p["failure_reason"]]
            retry_success = random.random() < spec["retry_success_p"]
            recovery_rows.append(dict(
                payment_id=p["payment_id"],
                failure_reason=p["failure_reason"],
                is_recoverable=spec["is_recoverable"],
                retry_would_succeed=retry_success,
                recommended_action=spec["action"],
            ))

    return orders, payments, recovery_rows


def _make_payment(orders, payments, merchant_id, cid, amount, ts, customer_device,
                   cust_instruments, force_success_p):
    order_id = rid("ord")
    payment_id = rid("pay")
    device_id = customer_device[cid]
    instrument_id = random.choice(cust_instruments[cid])

    if force_success_p is not None:
        success = random.random() < force_success_p
    else:
        success = random.random() > FAIL_RATE

    orders.append(dict(
        order_id=order_id, merchant_id=merchant_id, customer_id=cid,
        amount=amount, currency="INR", created_at=iso(ts),
    ))

    if success:
        auth_ts = ts + timedelta(seconds=random.randint(1, 5))
        cap_ts = auth_ts + timedelta(seconds=random.randint(1, 10))
        payments.append(dict(
            payment_id=payment_id, order_id=order_id, customer_id=cid,
            merchant_id=merchant_id, device_id=device_id, instrument_id=instrument_id,
            amount=amount, currency="INR", status="success", failure_reason="",
            created_at=iso(ts), authorized_at=iso(auth_ts), captured_at=iso(cap_ts),
        ))
    else:
        reason = random.choices(list(FAILURE_REASONS.keys()), weights=FAILURE_WEIGHTS)[0]
        payments.append(dict(
            payment_id=payment_id, order_id=order_id, customer_id=cid,
            merchant_id=merchant_id, device_id=device_id, instrument_id=instrument_id,
            amount=amount, currency="INR", status="failed", failure_reason=reason,
            created_at=iso(ts), authorized_at="", captured_at="",
        ))


def gen_refunds(payments):
    rows = []
    succeeded = [p for p in payments if p["status"] == "success"]
    n_refunds = int(len(succeeded) * REFUND_RATE)
    for p in random.sample(succeeded, n_refunds):
        full = random.random() < 0.4
        amt = p["amount"] if full else round(p["amount"] * random.uniform(0.2, 0.8), 2)
        refund_ts = datetime.fromisoformat(p["captured_at"]) + timedelta(
            days=random.randint(0, 5), hours=random.randint(0, 23))
        rows.append(dict(
            refund_id=rid("rfnd"), payment_id=p["payment_id"],
            amount=amt, reason=random.choice(["customer_request", "duplicate_charge",
                                               "product_return", "merchant_error"]),
            created_at=iso(refund_ts),
        ))
    return rows


def gen_fees(payments):
    rows = []
    for p in payments:
        if p["status"] != "success":
            continue
        fee = round(max(p["amount"] * 0.02, 2), 2)
        tax = round(fee * 0.18, 2)
        rows.append(dict(fee_id=rid("fee"), payment_id=p["payment_id"],
                          fee_amount=fee, tax_amount=tax, fee_type="gateway_fee"))
    return rows


def gen_settlements(payments, refunds, fees):
    """Groups successful payments per merchant per capture-day into a settlement,
    computes expected net, then emits settlements + settlement_payments + bank
    transactions, injecting one reconciliation anomaly into a subset of batches."""
    refund_by_payment = {}
    for r in refunds:
        refund_by_payment.setdefault(r["payment_id"], 0.0)
        refund_by_payment[r["payment_id"]] += r["amount"]
    fee_by_payment = {f["payment_id"]: (f["fee_amount"], f["tax_amount"]) for f in fees}

    batches = {}
    for p in payments:
        if p["status"] != "success":
            continue
        day = p["captured_at"][:10]
        batches.setdefault((p["merchant_id"], day), []).append(p)

    settlements, settlement_payments, bank_txns = [], [], []
    recon_labels, resolution_labels = [], []

    batch_keys = list(batches.keys())
    n_anomalous = int(len(batch_keys) * 0.30)
    anomalous_keys = set(random.sample(batch_keys, min(n_anomalous, len(batch_keys))))

    for (merchant_id, day), pays in batches.items():
        settlement_id = rid("sett")
        cap_day = datetime.fromisoformat(day)
        settlement_date = cap_day + timedelta(days=1)
        bank_date = settlement_date + timedelta(days=1)
        payment_ids = ";".join(p["payment_id"] for p in pays)

        case = random.choice(RECON_CASES) if (merchant_id, day) in anomalous_keys else None

        gross = sum(p["amount"] for p in pays)
        fee_total = sum(fee_by_payment.get(p["payment_id"], (0, 0))[0] for p in pays)
        tax_total = sum(fee_by_payment.get(p["payment_id"], (0, 0))[1] for p in pays)
        refund_total = sum(refund_by_payment.get(p["payment_id"], 0.0) for p in pays)
        expected_net = round(gross - fee_total - tax_total - refund_total, 2)

        if case == "missing_settlement":
            # No settlement or bank row at all -- these payments are successful but
            # unreferenced by any settlement. Detectable deterministically (payment
            # has no row in settlement_payments); root cause is nameable once found.
            recon_labels.append(dict(
                settlement_id=settlement_id, payment_ids=payment_ids,
                root_cause=case, expected_net=expected_net, actual_bank_amount="",
                is_explainable=True,
            ))
            continue

        settlements.append(dict(
            settlement_id=settlement_id, merchant_id=merchant_id,
            settlement_date=iso(settlement_date),
            gross_amount=round(gross, 2), fee_amount=round(fee_total, 2),
            tax_amount=round(tax_total, 2), net_amount=expected_net,
        ))
        for p in pays:
            settlement_payments.append(dict(settlement_id=settlement_id, payment_id=p["payment_id"]))
            if case == "duplicate_record" and p is pays[0]:
                settlement_payments.append(dict(settlement_id=settlement_id, payment_id=p["payment_id"]))

        actual_bank_amount = expected_net
        is_explainable = True
        utr = "UTR" + uuid.uuid4().hex[:12].upper()
        desc = f"RAZORPAY {settlement_id[-8:]} SETTLEMENT"
        split = False

        if case == "timing_skew":
            bank_date = bank_date + timedelta(days=random.choice([1, 2]))
        elif case == "partial_refund":
            extra_refund = round(random.choice(pays)["amount"] * random.uniform(0.1, 0.3), 2)
            actual_bank_amount = round(expected_net - extra_refund, 2)
        elif case == "duplicate_record":
            actual_bank_amount = round(expected_net - pays[0]["amount"], 2)
        elif case == "split_settlement":
            split = True
        elif case == "fee_discrepancy":
            delta = round(random.uniform(20, 150), 2)
            actual_bank_amount = round(expected_net - delta, 2)
        elif case == "bank_adjustment":
            delta = round(random.uniform(50, 500), 2)
            actual_bank_amount = round(expected_net - delta, 2)
            desc = f"RZP {settlement_id[-6:]} ADJ"
            is_explainable = False  # no adjustment ledger provided -- genuinely not derivable
        elif case == "currency_conversion":
            delta = round(expected_net * random.uniform(0.001, 0.006), 2)
            actual_bank_amount = round(expected_net - delta, 2)
            is_explainable = False  # no FX rate table provided -- genuinely not derivable

        if split:
            half = round(actual_bank_amount / 2, 2)
            btx1, btx2 = rid("btx"), rid("btx")
            bank_txns.append(dict(bank_txn_id=btx1, utr=utr, amount=half,
                                   value_date=iso(bank_date), description=desc + " PART1"))
            bank_txns.append(dict(bank_txn_id=btx2, utr="UTR" + uuid.uuid4().hex[:12].upper(),
                                   amount=actual_bank_amount - half, value_date=iso(bank_date),
                                   description=desc + " PART2"))
            resolution_labels.append(dict(bank_txn_id=btx1, settlement_id=settlement_id, match_type="split"))
            resolution_labels.append(dict(bank_txn_id=btx2, settlement_id=settlement_id, match_type="split"))
        else:
            btx = rid("btx")
            bank_txns.append(dict(bank_txn_id=btx, utr=utr, amount=actual_bank_amount,
                                   value_date=iso(bank_date), description=desc))
            resolution_labels.append(dict(bank_txn_id=btx, settlement_id=settlement_id,
                                           match_type=case or "exact"))

        recon_labels.append(dict(
            settlement_id=settlement_id, payment_ids=payment_ids,
            root_cause=case or "none",
            expected_net=expected_net, actual_bank_amount=actual_bank_amount,
            is_explainable=is_explainable,
        ))

    return settlements, settlement_payments, bank_txns, recon_labels, resolution_labels


def build_case_manifest(payments, risk_labels, recovery_rows, recon_labels):
    manifest = []
    ring_payment = next((p for p in payments if risk_labels.get(p["customer_id"], {}).get("pattern") == "fraud_ring"), None)
    benign_payment = next((p for p in payments if risk_labels.get(p["customer_id"], {}).get("pattern") == "benign_shared_device"), None)
    recoverable = next((r for r in recovery_rows if r["retry_would_succeed"]), None)
    unrecoverable = next((r for r in recovery_rows if not r["is_recoverable"]), None)
    explainable_recon = next((r for r in recon_labels if r["root_cause"] not in ("none", "") and r["is_explainable"]), None)
    unexplainable_recon = next((r for r in recon_labels if not r["is_explainable"]), None)

    for label, obj in [
        ("fraud_ring_example", ring_payment and {"payment_id": ring_payment["payment_id"]}),
        ("benign_shared_device_example", benign_payment and {"payment_id": benign_payment["payment_id"]}),
        ("recoverable_failure_example", recoverable),
        ("unrecoverable_failure_example", unrecoverable),
        ("explainable_exception_example", explainable_recon),
        ("honest_unexplained_exception_example", unexplainable_recon),
    ]:
        if obj:
            manifest.append(dict(case=label, **obj))
    return manifest


def main():
    merchants = gen_merchants()
    customers = gen_customers()
    devices, customer_device, risk_labels = gen_devices_and_rings(customers)
    instruments, cust_instruments = gen_instruments(customers)
    orders, payments, recovery_rows = gen_payments(
        merchants, customers, customer_device, cust_instruments, risk_labels)
    refunds = gen_refunds(payments)
    fees = gen_fees(payments)
    settlements, settlement_payments, bank_txns, recon_labels, resolution_labels = gen_settlements(payments, refunds, fees)

    write_csv(RAW / "merchants.csv", merchants, ["merchant_id", "name", "category", "created_at"])
    write_csv(RAW / "customers.csv", customers, ["customer_id", "name", "email", "created_at"])
    write_csv(RAW / "devices.csv", devices, ["device_id", "fingerprint", "first_seen_at"])
    write_csv(RAW / "payment_instruments.csv", instruments,
              ["instrument_id", "type", "masked_identifier", "customer_id"])
    write_csv(RAW / "orders.csv", orders,
              ["order_id", "merchant_id", "customer_id", "amount", "currency", "created_at"])
    write_csv(RAW / "payments.csv", payments,
              ["payment_id", "order_id", "customer_id", "merchant_id", "device_id", "instrument_id",
               "amount", "currency", "status", "failure_reason", "created_at", "authorized_at", "captured_at"])
    write_csv(RAW / "refunds.csv", refunds, ["refund_id", "payment_id", "amount", "reason", "created_at"])
    write_csv(RAW / "fees.csv", fees, ["fee_id", "payment_id", "fee_amount", "tax_amount", "fee_type"])
    write_csv(RAW / "settlements.csv", settlements,
              ["settlement_id", "merchant_id", "settlement_date", "gross_amount", "fee_amount",
               "tax_amount", "net_amount"])
    write_csv(RAW / "settlement_payments.csv", settlement_payments, ["settlement_id", "payment_id"])
    write_csv(RAW / "bank_transactions.csv", bank_txns,
              ["bank_txn_id", "utr", "amount", "value_date", "description"])

    risk_rows = [dict(customer_id=cid, **v) for cid, v in risk_labels.items()]
    write_csv(GT / "risk_labels.csv", risk_rows, ["customer_id", "is_fraud", "ring_id", "pattern"])
    write_csv(GT / "recovery_labels.csv", recovery_rows,
              ["payment_id", "failure_reason", "is_recoverable", "retry_would_succeed", "recommended_action"])
    write_csv(GT / "reconciliation_labels.csv", recon_labels,
              ["settlement_id", "payment_ids", "root_cause", "expected_net", "actual_bank_amount", "is_explainable"])
    write_csv(GT / "entity_resolution_labels.csv", resolution_labels,
              ["bank_txn_id", "settlement_id", "match_type"])

    manifest = build_case_manifest(payments, risk_labels, recovery_rows, recon_labels)
    GT.mkdir(parents=True, exist_ok=True)
    with open(GT / "case_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    n_fraud = sum(1 for v in risk_labels.values() if v["is_fraud"])
    n_benign_shared = sum(1 for v in risk_labels.values() if v["pattern"] == "benign_shared_device")
    n_unexplainable = sum(1 for r in recon_labels if not r["is_explainable"])
    print(f"merchants={len(merchants)} customers={len(customers)} devices={len(devices)}")
    print(f"orders={len(orders)} payments={len(payments)} "
          f"(success={sum(1 for p in payments if p['status']=='success')}, "
          f"failed={sum(1 for p in payments if p['status']=='failed')})")
    print(f"refunds={len(refunds)} fees={len(fees)}")
    print(f"settlements={len(settlements)} bank_txns={len(bank_txns)} "
          f"anomalous_settlements={sum(1 for r in recon_labels if r['root_cause']!='none')} "
          f"unexplainable={n_unexplainable}")
    print(f"fraud_customers={n_fraud} benign_shared_device_customers={n_benign_shared}")
    print(f"recovery_cases={len(recovery_rows)}")
    print(f"case_manifest -> {GT / 'case_manifest.json'}")


if __name__ == "__main__":
    main()
