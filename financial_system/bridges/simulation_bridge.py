"""
Simulation -> Heimdall bridge: transform layer.

Reads a completed `Simulation/` run's output directory (persons.csv,
merchants.csv, transactions.csv -- the schema documented in
`Simulation/docs/Design.md` and shown concretely in `Simulation/output/sample/`)
and writes a new directory shaped exactly like `financial_system/data/raw/`
-- the real input `financial_system/financial_state/builder.py` (Phase 1)
already knows how to ingest, completely unmodified.

This module is a pure, additive transform:
  - it never imports anything from `Simulation/`'s engine/world code, only
    reads the CSV files a finished run already wrote to disk;
  - it never imports or modifies anything under `financial_system/` other
    than reading the raw-CSV column names it must match (verified by hand
    against `financial_system/ingestion/*.py`, not guessed);
  - it writes only to a caller-supplied output directory, never to
    `financial_system/data/`.

WHY RECOVERY, NOT RISK OR CONTROLLER (see bridges/README.md for the full
reasoning): Risk's only nonzero signal (risk/runner.py's
`devices_with_sharers`) requires >=2 customers sharing one Device node --
i.e. real device-fingerprint/fraud-ring modeling. `Simulation/` has no
Device, PaymentInstrument, or fraud concept at all (persons.csv has none of
these columns). Recovery's decision logic (`recovery/signals.py`) reads
exactly three things from the graph: a Payment's `status`, its
`failure_reason`, and whether a sibling Payment on the same Order already
succeeded -- all three are things `Simulation/`'s `transactions.csv` either
IS (status, via `kind`) or trivially entails (failure_reason, via the one
mechanically-verified cause `Simulation/` actually models: `balance_before
< amount` -> `insufficient_funds`; no-siblings, via the 1-payment-per-order
convention this bridge adopts, matching Heimdall's own real dataset, which
is also 1:1 order:payment 1000/1000 times).

WHAT THIS BRIDGE FABRICATES, AND WHY (the one genuine gap): Heimdall's
`payment_ingestion.py` requires `device_id` and `instrument_id` to be valid
foreign keys into `devices` / `payment_instruments` -- fields Recovery's own
decision logic (`recovery/signals.py`) never reads, but that ingestion
requires structurally regardless of domain. Since `Simulation/` has no
device/instrument concept, this bridge synthesizes exactly one placeholder
Device and one placeholder PaymentInstrument per simulated Person, derived
deterministically from `person_id`, carrying no signal whatsoever (fixed
fingerprint/type/masked_identifier strings). This is a structural filler
for referential integrity only -- flagged here, in the field-mapping table
in README.md, and again in the run report, so it is never mistaken for
simulated device data. A direct consequence: Risk's shared-device signal
can never fire on bridged data (every device has exactly one owner), which
is exactly why Risk was not the domain chosen.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

# Column order for each Heimdall raw CSV this bridge writes -- copied by hand
# from the header row of financial_system/data/raw/*.csv (read, not guessed),
# so a byte-for-byte-compatible file comes out the other end.
_HEIMDALL_HEADERS = {
    "merchants.csv": ["merchant_id", "name", "category", "created_at"],
    "customers.csv": ["customer_id", "name", "email", "created_at"],
    "devices.csv": ["device_id", "fingerprint", "first_seen_at"],
    "payment_instruments.csv": ["instrument_id", "type", "masked_identifier", "customer_id"],
    "orders.csv": ["order_id", "merchant_id", "customer_id", "amount", "currency", "created_at"],
    "payments.csv": [
        "payment_id", "order_id", "customer_id", "merchant_id", "device_id", "instrument_id",
        "amount", "currency", "status", "failure_reason", "created_at", "authorized_at", "captured_at",
    ],
    # Not modeled by Simulation/ at all (no refund, fee, settlement, or bank-
    # transaction concept in transactions.csv's `kind` vocabulary) -- written
    # as header-only files so Phase 1's fixed ingestion-step list still runs
    # cleanly end to end, unmodified, exactly as it does on a real dataset
    # that happens to have zero rows of one type.
    "refunds.csv": ["refund_id", "payment_id", "amount", "reason", "created_at"],
    "fees.csv": ["fee_id", "payment_id", "fee_amount", "tax_amount", "fee_type"],
    "settlements.csv": [
        "settlement_id", "merchant_id", "settlement_date", "gross_amount", "fee_amount",
        "tax_amount", "net_amount",
    ],
    "settlement_payments.csv": ["settlement_id", "payment_id"],
    "bank_transactions.csv": ["bank_txn_id", "utr", "amount", "value_date", "description"],
}

# The only causal failure mechanism Simulation/'s engine actually implements
# (Simulation/docs/Research.md, Simulation/docs/Memory.md, and confirmed
# directly against a real run below): a purchase transaction whose
# balance_before < amount. This is the one Heimdall FAILURE_TAXONOMY (see
# financial_system/recovery/signals.py) category this bridge can honestly
# claim -- no other category is ever produced by Simulation/, and this
# bridge does not invent any.
SIMULATION_FAILURE_REASON = "insufficient_funds"

CURRENCY = "INR"  # Simulation/ has no currency field; Heimdall requires one. Fixed assumption, documented.


@dataclass
class BridgeTransformReport:
    persons_read: int = 0
    merchants_read: int = 0
    transactions_read: int = 0
    payments_written: int = 0
    orders_written: int = 0
    customers_written: int = 0
    merchants_written: int = 0
    devices_written: int = 0
    instruments_written: int = 0
    skipped_transaction_kinds: dict = field(default_factory=dict)  # kind -> count, e.g. salary/settlement/sweep
    fabricated_fields: list = field(default_factory=list)


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, header: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def transform_simulation_output(sim_outdir: Path, bridge_raw_dir: Path) -> BridgeTransformReport:
    """Reads a completed Simulation/ run's output directory and writes a new
    directory in financial_system/data/raw/'s exact schema. Pure transform;
    touches no file under financial_system/ or Simulation/."""
    sim_outdir = Path(sim_outdir)
    bridge_raw_dir = Path(bridge_raw_dir)
    bridge_raw_dir.mkdir(parents=True, exist_ok=True)

    persons = _read_csv(sim_outdir / "persons.csv")
    merchants = _read_csv(sim_outdir / "merchants.csv")
    transactions = _read_csv(sim_outdir / "transactions.csv")

    report = BridgeTransformReport(
        persons_read=len(persons), merchants_read=len(merchants), transactions_read=len(transactions),
    )

    # Simulation/ has no entity "created_at" for Person/Merchant -- the
    # simulated world begins existing at the run's own earliest observed
    # transaction timestamp. Used as a placeholder creation date for every
    # reference entity below (documented fabrication, not simulated data).
    earliest_ts = min((t["timestamp"] for t in transactions), default="1970-01-01T00:00:00+00:00")
    report.fabricated_fields.append(
        f"customers.created_at, merchants.created_at, devices.first_seen_at := earliest transaction "
        f"timestamp in the run ({earliest_ts}) -- Simulation/'s persons.csv/merchants.csv carry no "
        f"creation-date field at all"
    )
    report.fabricated_fields.append(
        "customers.email := '<person_id>@simulation.bridge.local' -- Simulation/ has no email field"
    )
    report.fabricated_fields.append(
        "devices, payment_instruments (one placeholder each per Person, keyed off person_id) -- "
        "Simulation/ has no device or payment-instrument concept whatsoever; these exist purely to "
        "satisfy Heimdall's payment_ingestion.py foreign-key requirement and carry zero signal. "
        "recovery/signals.py never reads either field, confirmed by reading it, so this fabrication "
        "cannot influence a Recovery decision -- it would, however, make Risk's shared-device signal "
        "vacuous on this data (every device has exactly one owner), which is why Risk was not chosen."
    )
    report.fabricated_fields.append(
        f"payments.currency / orders.currency := {CURRENCY!r} (fixed) -- Simulation/ has no currency "
        f"field, financial_system/'s payment_ingestion.py defaults to INR too if unset, so this matches "
        f"Heimdall's own default rather than inventing a new convention"
    )

    # -- customers.csv (Person -> Customer), devices.csv, payment_instruments.csv --
    customer_rows, device_rows, instrument_rows = [], [], []
    for p in persons:
        pid = p["person_id"]
        customer_rows.append({
            "customer_id": pid, "name": p.get("name", ""),
            "email": f"{pid}@simulation.bridge.local", "created_at": earliest_ts,
        })
        device_rows.append({
            "device_id": f"dev_bridge_{pid}", "fingerprint": "bridge-placeholder-no-device-signal",
            "first_seen_at": earliest_ts,
        })
        instrument_rows.append({
            "instrument_id": f"instr_bridge_{pid}", "type": "bridge-placeholder",
            "masked_identifier": "N/A", "customer_id": pid,
        })
    _write_csv(bridge_raw_dir / "customers.csv", _HEIMDALL_HEADERS["customers.csv"], customer_rows)
    _write_csv(bridge_raw_dir / "devices.csv", _HEIMDALL_HEADERS["devices.csv"], device_rows)
    _write_csv(bridge_raw_dir / "payment_instruments.csv", _HEIMDALL_HEADERS["payment_instruments.csv"],
               instrument_rows)
    report.customers_written = len(customer_rows)
    report.devices_written = len(device_rows)
    report.instruments_written = len(instrument_rows)

    # -- merchants.csv (Merchant -> Merchant, direct) --
    merchant_rows = [
        {"merchant_id": m["merchant_id"], "name": m.get("name", ""), "category": m.get("category", ""),
         "created_at": earliest_ts}
        for m in merchants
    ]
    _write_csv(bridge_raw_dir / "merchants.csv", _HEIMDALL_HEADERS["merchants.csv"], merchant_rows)
    report.merchants_written = len(merchant_rows)

    person_ids = {p["person_id"] for p in persons}
    merchant_ids = {m["merchant_id"] for m in merchants}

    # -- orders.csv + payments.csv, one order+payment per person->merchant
    # transaction (kind in {purchase, payment_failure}). Everything else in
    # Simulation/'s kind vocabulary (salary, settlement, household_sweep,
    # savings_sweep, org_funding) is not a customer purchase and is skipped
    # -- not a Heimdall Payment/Order at all, on either side of this bridge.
    order_rows, payment_rows = [], []
    skipped: dict[str, int] = {}
    for t in transactions:
        kind = t["kind"]
        if kind not in ("purchase", "payment_failure"):
            skipped[kind] = skipped.get(kind, 0) + 1
            continue
        from_id, to_id = t["from_id"], t["to_id"]
        # Guard, not expected to ever fire on Simulation/'s own transaction
        # generation (purchases are always person->merchant) -- if it did,
        # that transaction is skipped rather than silently mis-mapped.
        if from_id not in person_ids or to_id not in merchant_ids:
            skipped[f"{kind} (non person->merchant, skipped)"] = \
                skipped.get(f"{kind} (non person->merchant, skipped)", 0) + 1
            continue

        txn_id = t["transaction_id"]
        order_id = f"ord_bridge_{txn_id}"
        payment_id = f"pay_bridge_{txn_id}"
        amount = t["amount"]
        ts = t["timestamp"]
        is_failed = kind == "payment_failure"

        order_rows.append({
            "order_id": order_id, "merchant_id": to_id, "customer_id": from_id,
            "amount": amount, "currency": CURRENCY, "created_at": ts,
        })
        payment_rows.append({
            "payment_id": payment_id, "order_id": order_id, "customer_id": from_id, "merchant_id": to_id,
            "device_id": f"dev_bridge_{from_id}", "instrument_id": f"instr_bridge_{from_id}",
            "amount": amount, "currency": CURRENCY,
            "status": "failed" if is_failed else "success",
            "failure_reason": SIMULATION_FAILURE_REASON if is_failed else "",
            "created_at": ts, "authorized_at": "" if is_failed else ts, "captured_at": "" if is_failed else ts,
        })

    _write_csv(bridge_raw_dir / "orders.csv", _HEIMDALL_HEADERS["orders.csv"], order_rows)
    _write_csv(bridge_raw_dir / "payments.csv", _HEIMDALL_HEADERS["payments.csv"], payment_rows)
    report.orders_written = len(order_rows)
    report.payments_written = len(payment_rows)
    report.skipped_transaction_kinds = skipped

    # -- concepts Simulation/ does not model at all: written header-only so
    # Phase 1's fixed ingestion-step list (financial_state/builder.py's
    # _INGESTION_STEPS) still runs unmodified end to end.
    for name in ("refunds.csv", "fees.csv", "settlements.csv", "settlement_payments.csv", "bank_transactions.csv"):
        _write_csv(bridge_raw_dir / name, _HEIMDALL_HEADERS[name], [])

    return report
