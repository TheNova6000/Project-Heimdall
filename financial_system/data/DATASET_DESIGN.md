# Synthetic Financial Universe — Design

Two directories come out of `data_generator/generate_dataset.py`:

- **`data/raw/`** — what the ingestion agents actually read. This is "reality":
  messy, cross-referenced by ID, occasionally contradictory. No labels in here.
- **`data/ground_truth/`** — held out. Used only to score Risk/Controller/Recovery
  output and to pick demo cases. Nothing in `financial_system/` outside the scoring
  code and the demo script should ever read this directory.

Fixed random seed (`SEED = 42`) governs every `random.*` call, so counts, case-type
distribution, and which entities land in which scenario are reproducible across
runs -- "we detected 41/44 fraud rings" is a stable, repeatable claim, not a lucky
roll. Entity ids are not reproducible: they're generated with `uuid.uuid4()`,
which draws from OS entropy and ignores `random.seed()`, so re-running the
generator produces the same shape with different literal ids. That's fine as
long as raw/ and ground_truth/ are regenerated together and nothing downstream
hardcodes an id from a prior run -- just don't expect `case_manifest.json`'s
payment_ids to match between two separate generator runs.

## Realism decision: what's given vs. what must be resolved

Payment → Order and Payment → Settlement linkage are **given directly**
(`settlement_payments.csv`) — this mirrors an actual gateway settlement report,
which always lists the payment IDs in a batch. Making the whole chain artificially
obfuscated (as in the original "PAY123→ORD777→SET928→UTR" sketch) doesn't reflect
how the data actually shows up, and it dilutes the one linkage that's genuinely
hard in real reconciliation:

**Settlement → BankTransaction is NOT given.** Bank statements only carry a UTR and
a free-text `description` field, sometimes containing a clean settlement reference,
sometimes a garbled fragment, sometimes nothing recognizable. That's the one
entity-resolution problem worth building deterministic+probabilistic+agentic
matching for (§ Entity Resolution Agent in `ARCHITECTURE.md`) — matching on
amount proximity, date proximity, and partial string match against `description`,
each producing a `matches` edge with a `confidence` and `evidence[]`.

## Entities & volumes

| Entity | Count | File |
|---|---|---|
| Merchants | 25 | `merchants.csv` |
| Customers | 400 | `customers.csv` |
| Devices | ~375 (1 per customer, fewer after ring/pair device-sharing merges) | `devices.csv` |
| Payment instruments | ~450 | `payment_instruments.csv` |
| Orders | 1000 | `orders.csv` |
| Payments | 1000 | `payments.csv` |
| Refunds | ~85 (subset of successful payments) | `refunds.csv` |
| Fees | one per successful payment | `fees.csv` |
| Settlements | ~1 per merchant per active day | `settlements.csv` + `settlement_payments.csv` |
| Bank transactions | ~1 per settlement, some split/missing | `bank_transactions.csv` |

Order window: last 60 days ending on the generation date. Settlement is T+1,
bank credit is T+2 from capture, in the normal case.

## Case taxonomy (this is the part that makes the system testable)

### A. Normal (baseline, ~70% of payments)
Clean lifecycle: capture → fee/tax deducted → settled → bank credit matches
`amount - fee - tax(- refund)` exactly, on schedule. This is what "nothing to
investigate" should look like — if the system flags these, that's a false positive.

### B. Reconciliation cases (injected into a subset of settlements)
| Root cause | What happens | Should the system fully explain it? |
|---|---|---|
| `timing_skew` | bank credit lands T+2/T+3 instead of T+1, amount matches | Yes |
| `duplicate_record` | same payment listed twice in a settlement batch | Yes — the duplicate row in `settlement_payments.csv` is itself the (nameable) explanation |
| `missing_settlement` | eligible payment never gets a settlement row at all | Yes — the payment's absence from `settlement_payments.csv` is itself the (nameable) explanation |
| `split_settlement` | one settlement paid out as two bank transactions | Yes, sum matches |
| `bank_adjustment` | bank subtracts an extra, undocumented adjustment | **No** — no adjustment ledger is provided; this is the case that tests "honest incompleteness" instead of a confident wrong guess |
| `currency_conversion` | small FX-driven delta on a cross-currency payment | **No** — no FX rate table is provided, so the exact delta isn't derivable from given data either |
| `partial_refund` | bank amount is short by an extra delta framed as a "refund" | **No** (corrected, see below) — the delta is computed in-memory by the generator and never written to `refunds.csv`, so no raw record backs it |
| `fee_discrepancy` | bank amount is short by an extra delta framed as a "fee correction" | **No** (corrected, see below) — same issue: the delta never lands in `fees.csv` |

**Correction (found while designing Phase 4's evidence retrieval):** `partial_refund`
and `fee_discrepancy` were originally documented and labeled `is_explainable=true`,
but tracing the generator showed their deltas are local variables in
`generate_dataset.py` that never get written to `refunds.csv`/`fees.csv` — so, as
generated, no raw record actually explains either one, same as `bank_adjustment`/
`currency_conversion`. `ground_truth/reconciliation_labels.csv` has been patched
(is_explainable flipped to `false` for these two root causes only, 52 rows) without
touching `raw/` or regenerating — Phase 1-3's passing baseline and every id are
unaffected. The generator's own comments/names for these two cases still describe
the original (unimplemented) intent; a future pass could make them genuinely
explainable by actually writing the backing record, but that's a `raw/` change and
hasn't been done.

### C. Risk cases (injected into customer/device/instrument assignment)
| Pattern | Shape | Ground truth |
|---|---|---|
| `fraud_ring` (6 rings, 3–5 customers each) | shared device and/or instrument, accounts created shortly before first payment, high velocity, clustered amounts | `is_fraud = true` |
| `benign_shared_device` (8 pairs) | 2 customers share a device, older accounts, low velocity, dissimilar amounts, spread over weeks | `is_fraud = false` — exists specifically to punish a Risk Agent that flags on shared-device alone |
| everything else | unique device per customer | `is_fraud = false` |

### D. Recovery cases (drawn from the 15% of payments that fail)
| `failure_reason` | `is_recoverable` | `retry_would_succeed` (hidden, used by Verification) |
|---|---|---|
| `technical_failure` / `timeout` | true | mostly true |
| `insufficient_funds` | true (after delay) | mixed |
| `authentication_failure` | true (retry w/ different method) | mixed |
| `issuer_declined` | sometimes | mostly false |
| `risk_block` | false via retry — needs review | false |
| `expired` | false — needs new customer action | false |

## Ground truth files

- `ground_truth/reconciliation_labels.csv` — settlement_id, root_cause, expected_net,
  actual_bank_amount, is_explainable
- `ground_truth/entity_resolution_labels.csv` — bank_txn_id, settlement_id, match_type —
  the answer key for the Settlement→BankTransaction matching problem described above;
  scores the Entity Resolution Agent's `matches` edges, never read by the agent itself
- `ground_truth/risk_labels.csv` — customer_id, is_fraud, ring_id (nullable), pattern
- `ground_truth/recovery_labels.csv` — payment_id, is_recoverable, retry_would_succeed,
  recommended_action
- `ground_truth/case_manifest.json` — ~8 hand-picked payment_ids spanning every
  category above, for the demo script ("one payment, three perspectives")

## What this enables

Precision/recall for Risk (against `is_fraud`, including the benign-shared-device
traps), match rate + honest-exception rate for Controller (against
`is_explainable`), recovery rate + false-retry rate for Recovery (against
`retry_would_succeed`) — the exact metrics the buildathon tracks ask for, computed
against a held-out answer key instead of eyeballed from a demo run.
