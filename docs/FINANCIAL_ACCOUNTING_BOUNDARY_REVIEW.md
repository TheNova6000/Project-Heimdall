# Financial Accounting Boundary Review

Written per the user's explicit direction, stepping back from temporal
architecture to ask a different question: does the current financial
world model actually represent *money*, or does it represent the
*operational lifecycle* money happens to move through? Grounded entirely
in the actual current Phase 1-10 system (every claim below is a direct
code read or a direct computation against the real dataset, not a
guess), plus the standing deferred-ledger decision
(`MIGRATION_DESIGN.md` line 210: "no demonstrated failure justifies it
yet"). This document implements nothing. It answers the fifteen
questions and reaches a recommendation among A/B/C.

## Grounding: three things checked directly, not assumed

**1. `reconcile_settlement()` checks exactly one arithmetic invariant.**
Read directly (`reconciliation/deterministic.py:41-88`): expected =
`Settlement.net_amount` (trusted as given, never independently derived);
actual = `sum(linked BankTransaction.amount)`; the only adjustment
applied is a duplicate-line-item correction (a payment counted twice
under a settlement's `contains` edges). Fees and Refunds are never read
in this function at all.

**2. Fees and Refunds are visible evidence, not value movements.**
`financial_graph/queries.py::reconciliation_neighborhood()` explicitly
surfaces a settlement's payments' `generates` (Fee) and `refunded_by`
(Refund) edges as facts a human or Discovery.AI can read
(`queries.py:111-114`) -- but nothing in `reconcile_settlement()`'s own
arithmetic nets them into the expected/actual comparison. A fee or a
refund is something the system can *point to*, never something it
*subtracts*.

**3. Two internal-consistency invariants were checked directly against
the raw dataset for the first time this session, and both fail at real
scale:**

```
gross_amount - fee_amount - tax_amount == net_amount   -->  77/610 settlements violate this (12.6%)
sum(linked Payment.amount) == gross_amount               -->  19/610 naive sums disagree (3.1%)
```

**Correction, made once the check was actually implemented
(`reconciliation/accounting_consistency.py`,
`accounting_consistency_test.py`): the second number was an artifact.**
Summed naively, without deduplicating repeated `settlement_payments`
rows, 19 settlements disagree -- but that 19 turns out to be exactly the
19 already-known `duplicate_record` cases (reconcile_settlement()'s own
docstring already documents this table has no PK on
`(settlement_id, payment_id)` by design). Verified directly against
every real `duplicate_record`-labeled settlement: `gross_amount` matches
`sum(DISTINCT linked payments)` exactly, every time. Once deduplicated
correctly, `sum(linked Payment.amount) == gross_amount` holds for
**all 610 real settlements** -- zero violations. Left visible here,
struck through in effect rather than deleted, because the correction
itself is evidence of exactly the discipline this project has tried to
hold throughout: an inaccurate claim gets fixed the moment better
evidence exists, not left standing because it was already published.

Only the first invariant -- `gross_amount - fee_amount - tax_amount ==
net_amount`, unaffected by the deduplication question -- turned out to be
a real, previously-undetected gap. Neither check exists anywhere in the
codebase before this session -- `Settlement`'s four amount fields are
stored, but nothing ever verified they agree with each other, even
though all four are present on the same row.

**4. `reconciliation_labels.csv`'s own ground-truth taxonomy (635
labeled settlements) is the single most important piece of evidence in
this review** -- it's the dataset's own designer already having drawn
the boundary this review is asking about:

```
none                 445   -- clean, no accounting complexity
partial_refund         31  -- a REFUND that doesn't fully reverse a payment
currency_conversion    27  -- a conversion RATE, not just an amount
missing_settlement     25  -- money captured, not yet (or never) settled
bank_adjustment        23  -- a bank-side correction with no payment-side event
split_settlement        23  -- ONE settlement's money spread across MULTIPLE payments' worth, non-trivially
fee_discrepancy         21  -- the fee actually deducted != the fee recorded
timing_skew              21  -- a real match, observed across a delay
duplicate_record         19  -- the one category reconcile_settlement() actually handles
```

Eight of nine categories describe exactly the kind of value-flow
questions -- not lifecycle questions -- the user's framing raised:
partial refunds, currency conversion, fee discrepancies, and splits are
all *money not going where a naive lifecycle model would expect*, not
*a payment stuck in the wrong operational state*. The dataset already
anticipated this distinction; the reconciliation code built on top of it
has only ever closed one of the nine categories deterministically.

## The fifteen questions

**1. What does `Payment.amount` actually mean?**
The amount authorized/captured for one payment attempt -- a single
scalar, no currency-conversion structure (`amount: Decimal, currency:
str` -- one currency per payment, `financial_state/models.py:78-79`).
`currency_conversion` (27 labeled cases) already stresses this: nothing
in `Payment` or `Settlement` carries an exchange rate or a
"amount-in-settlement-currency" distinct from "amount-in-payment-currency."

**2. What does `Settlement.amount` mean?**
Four separate scalars (`gross_amount`, `fee_amount`, `tax_amount`,
`net_amount`) that, per the grounding above, are not currently checked
to agree with each other, let alone with the payments they claim to
settle.

**3. Are fees value movements or attributes?**
Modeled as an attribute today (a `Fee` row with a `generates` edge from
its `Payment`) -- but the ground truth's `fee_discrepancy` category (21
cases) treats a fee as something whose *value* can be wrong relative to
what should have been deducted, which is a value-movement question, not
an attribute question. The model's shape doesn't prevent representing
this correctly; the reconciliation *arithmetic* just doesn't read `Fee`
at all yet.

**4. Are refunds represented as negative value movements?**
No -- `Refund` is a positive `Decimal` amount on its own row, linked by
a `refunded_by` edge, never subtracted from anything. `partial_refund`
(31 cases, the single largest non-`none` category) is exactly the
scenario this absence would break on: a refund that's smaller than the
original payment, where "how much of the original payment's value is
still outstanding" is a real, currently-unanswerable question from the
model alone.

**5. Can one payment produce multiple financial movements?**
Structurally yes -- a `Payment` can have edges to multiple `Fee` rows
and (per the schema) multiple `Refund` rows. Whether the *dataset*
exercises multiple refunds per payment wasn't checked here (out of
scope for this pass); the schema doesn't prevent it.

**6. Can one settlement contain partial payment amounts?**
No -- `SettlementPayment` is a pure junction (`settlement_id,
payment_id`, no amount column at all,
`financial_state/models.py:117-124`). A settlement either contains a
payment or it doesn't; there's no way to represent "60% of this
payment's value settled here, 40% settled elsewhere." `split_settlement`
(23 cases) is very likely stressing exactly this absence -- a single
payment's value legitimately spread across settlement boundaries in a
way the junction table has no field to record.

**7. Where does money exist before settlement?**
Nowhere, explicitly. A captured `Payment` has no "held/in-transit/escrow"
state of its own -- `status="success"` is the only signal, and it says
nothing about whether the money has moved from customer to platform to
merchant. `missing_settlement` (25 cases) is the ground truth's own name
for this exact gap: a captured payment with no settlement yet is
indistinguishable, in the current model, from a captured payment that
will never settle.

**8. Who owns the money at each stage?**
Implicit, never modeled: `Payment.merchant_id`/`customer_id` and
`Settlement.merchant_id` exist, but there's no entity representing "the
platform's own custody of the money between capture and settlement" --
no escrow account, no intermediary balance. Ownership is inferred from
which foreign key happens to be set on which row, not asserted as a
first-class fact.

**9. Can every financial movement be expressed as debit/credit?**
Not currently, because nothing in the schema requires a movement to
balance against anything. A `Fee` row states a fee happened; it doesn't
require a corresponding entry saying which account received it. Building
this would be a real, structural addition (an `Account` entity + posting
rules), not a relabeling of what exists.

**10. What invariant should always balance?**
At minimum, per the grounding above, two invariants that are checkable
*today*, with the fields already on hand, and currently unchecked
anywhere: `gross_amount - fee_amount - tax_amount == net_amount`, and
`sum(linked Payment.amount) == gross_amount` (modulo legitimate
`duplicate_record`/`split_settlement` cases). A full double-entry
invariant (sum of debits == sum of credits, globally) is a much larger
claim this review does not recommend committing to yet -- see the
recommendation.

**11. What happens when settlement ≠ captured amount?**
Today: `reconcile_settlement()` reports `UNEXPLAINED` (or
`PARTIALLY_EXPLAINED` if a duplicate explains part of it) and, when
`investigate=True`, hands the gap to Discovery.AI to narrate. There is no
deterministic *accounting* explanation attempted for fee/refund/
conversion-driven gaps -- only the one duplicate-record case is resolved
by code; the other seven non-`none` categories are, as currently built,
either unexplained by 4A or dependent on 4B's narrative, never on an
expanded arithmetic model.

**12. What happens with partial settlement?**
Not representable -- per question 6, `SettlementPayment` has no amount
field. `split_settlement`'s 23 cases exist in the ground truth without a
corresponding structural capability to model them precisely; whatever
Controller currently does with them is working around the model's shape,
not through it.

**13. What happens with reversal?**
Genuinely unsupported at the event-sourcing layer too --
`TEMPORAL_ADVERSARIAL_REVIEW.md`'s own hardest-scenario walkthrough
already found this precisely: no event type for a settlement reversal
exists in the closed taxonomy (`events/taxonomy.py`), confirmed again
here as consistent with the accounting model having no representation
for it either. Two independent reviews, from two different angles,
converging on the same boundary.

**14. What happens with transfer/split settlement?**
Same answer as question 12 -- no representation.

**15. What is the relationship between operational reconciliation and
accounting reconciliation?**
This review's central finding, stated precisely: **today there is only
operational reconciliation.** "Operational reconciliation" (this
system's actual, current behavior) asks *"does the settlement's claimed
net amount match what the bank deposited, allowing for one specific,
coded exception (duplicates)?"* -- a lifecycle question, answerable by
walking `Payment -> Settlement -> BankTransaction` edges. "Accounting
reconciliation" would ask *"does every value movement -- capture, fee,
refund, conversion, settlement, deposit -- net to zero across the whole
chain?"* -- a value-conservation question, requiring debits and credits
that balance, which nothing in this system currently asserts, checks, or
even has the vocabulary (an `Account` entity) to state.

## Which of these does the product actually need to demonstrate?

The buildathon framing this whole project was built around
(`ARCHITECTURE.md`'s own "four kinds of intelligence" -- deterministic,
graph/relational, investigative, operational) was never staked on a full
accounting model; it was staked on demonstrating that a durable,
temporally-honest event history plus a disciplined reasoning boundary
can explain *why* a financial exception occurred, with Discovery.AI doing
the explaining exactly where deterministic code runs out. Everything
built through this session's four temporal checkpoints strengthens that
story. A full double-entry ledger would not make that story better -- it
would replace one large, already-proven subsystem's remaining
implementation time with a different, unproven one.

## Recommendation: **C, with one concrete B-lite exception named precisely**

**C -- a full double-entry ledger belongs outside this buildathon.** The
grounding above is the reason, not a hunch: building one means a new
`Account` entity, posting rules for every money-touching event type
(`PaymentCaptured`, `FeeRecorded`, `RefundRecorded`, `SettlementReceived`,
`BankTransactionRecorded` would all need to become balanced postings, not
observations), and a global debit==credit invariant enforced at the
event-store write boundary -- a subsystem comparable in size to the
entire temporal migration this session just finished proving, for a
payoff (mechanically explaining `fee_discrepancy`/`partial_refund`/
`currency_conversion`/`split_settlement` instead of handing them to
Discovery.AI) that the project's own architecture already treats as
Discovery.AI's job, not deterministic code's job, everywhere else in the
system (`ARCHITECTURE.md`'s kind-1-vs-kind-3 boundary, unchanged and
correct throughout this entire project).

**The one piece of B worth naming, because it's real, cheap, and already
found:** the two internal-consistency invariants from the grounding
section (`gross - fee - tax == net`, `sum(payments) == gross`) cost
nothing structurally -- no new entity, no new event type, no ledger --
and would convert a currently-silent 12.6%/3.1% data-quality gap into an
explicit, reportable fact. This is not "a minimal accounting model"; it's
tightening the *existing* reconciliation arithmetic to check numbers it
already has on hand. Whether to build even this much is explicitly left
open, per the user's own instruction not to implement from this
document -- named as the cheapest available next step if the answer to
"do we need any of this" turns out to be yes, not proposed as something
this review has already decided to do.

## What this review deliberately does not settle

- Whether the two named internal-consistency checks get implemented.
- Whether `split_settlement`/`partial_refund`'s structural gaps
  (`SettlementPayment` having no amount field) are worth closing even
  without a full ledger.
- Any change to `reconciliation/deterministic.py`, `financial_state/models.py`,
  or any event type.
- The Discovery.AI dual-graph diagram from the user's own message
  (operational graph + accounting graph, both queryable) -- an
  interesting, real architectural option, but one this review does not
  evaluate in depth, since it presupposes an accounting graph this review
  recommends against building for this project's remaining scope.

Per the user's own framing: the temporal architecture answered *"what
happened, when, what did the system decide, what did it do, and what
happened afterward."* This review's answer to *"where did the money
actually go"* is: **the system can point to where the evidence lives
(Fee/Refund/BankTransaction nodes, one edge away from every Payment and
Settlement), but cannot yet prove the money balances -- and, per the
recommendation above, proving that mechanically is not where this
project's remaining effort belongs.** The narrative half of that
question already belongs to Discovery.AI, exactly where the architecture
has consistently placed everything a deterministic invariant can't
settle.

## Implementation (this checkpoint)

Per the user's explicit go-ahead -- C, with the B-lite invariant checks
as the next and, per the user's own framing, likely last cheap
architectural step before returning to the product: implemented exactly
the two named checks, nothing beyond them.
`financial_system/reconciliation/accounting_consistency.py`'s
`check_accounting_consistency(state, settlement_id) ->
AccountingConsistencyResult` (`status: PASS | EXCEPTION`, `exceptions:
list[NET_AMOUNT_MISMATCH | PAYMENT_SUM_MISMATCH]`). Deliberately
standalone -- reads `FinancialStateStore` directly (Settlement's graph
node only ever carried `net_amount`/`settlement_date`, never
gross/fee/tax, so extending it would have touched shared graph-building
infrastructure for a check this narrow); not imported by
`reconciliation/controller.py` or `reconciliation/deterministic.py` at
all, confirmed by grep. Controller's `decision`/`decision_score`/
`proposed_action` and Phase 5's 607/610 baseline are untouched --
re-verified this session, unchanged.

`accounting_consistency_test.py`, 8 gates, all PASS: the full 610-
settlement corpus cross-tabulated against `reconciliation_labels.csv`'s
own root_cause taxonomy (533 PASS, 77 `NET_AMOUNT_MISMATCH`, 0
`PAYMENT_SUM_MISMATCH`); a real clean settlement passing both; a real
settlement failing exactly one invariant; a real `duplicate_record`
settlement confirmed NOT to misfire `PAYMENT_SUM_MISMATCH` (the
duplicate-counting scenario the user named explicitly); every real
`split_settlement` case checked and confirmed not to misfire either --
an empirical property of this dataset's construction, named as such, not
as a guarantee the check makes in general (`SettlementPayment` still has
no amount field); two synthetic fixtures proving the mechanism itself can
produce a bare `PAYMENT_SUM_MISMATCH` and both exceptions simultaneously,
since the real corpus never exercises either on its own; and
`missing_settlement`'s own `SETTLEMENT_NOT_FOUND` handling.

**A real correction made during this implementation, not before it**:
the review's own original "19/610 payment-sum mismatches" grounding
figure did not survive contact with the actual implementation -- see the
correction inline above. `gross_amount` already agrees with the sum of
distinct linked payments across the entire real corpus; the only genuine
gap this checkpoint closed is the `net = gross - fee - tax` invariant,
now checkable and confirmed to fail on 77 real settlements, 62 of them
inside the `none` ("no reconciliation exception") category -- the
sharpest evidence in this whole review that operational cleanliness and
accounting self-consistency are genuinely different questions, exactly
as the review argued in the abstract and now shows concretely.
