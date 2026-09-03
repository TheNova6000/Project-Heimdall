# Research — Financial World Simulation (Phase 3)

Written as part of a bounded "research + narrow, cited implementation" task
(Phases.md Phase 3: "Replace Phase 1's placeholder/assumption-labeled
probability rules with research-grounded ones where real sources exist...
each swap cited, not assumed"). Per the task brief that authorized this
work, external research (WebSearch/WebFetch against public sources —
academic papers, central bank/regulator publications, industry reports) is
in scope for this specific task; no dataset was bulk-downloaded (see
"What was not downloaded, and why" at the end).

This document has three parts:
- **Part A** — real research findings across five areas, each with the
  actual reported number/range, its source, and an honest note on how
  directly (or not) it maps onto this simulation.
- **Part B** — what, if anything, was changed in the running code because
  of Part A, with exact before/after values and inline citations.
- **Part C** — design-only proposals for fraud, credit scoring, and loan
  mechanics (NOT implemented — Phases.md Phase 3+/4/Beyond-Phase-6
  territory), grounded in Part A's findings.

A methodological caveat that applies throughout: the WebFetch tool
available in this session could not render several primary-source PDFs in
this environment (Federal Reserve, NBER, and arXiv PDFs consistently came
back as unparsed binary/stream data rather than text, apparently a
poppler/PDF-text-extraction limitation of this environment, not a content
problem). Where a finding rests on a PDF that could not be independently
re-verified by direct text extraction, it is flagged as coming from
WebSearch's synthesized summary of the source rather than a firsthand
quote — still a real citation to a real, named, dated publication, but
with weaker verification than the findings pulled from ordinary HTML pages
(which WebFetch parsed without issue, e.g. federalreserve.gov, Stripe,
Kansas City Fed). This distinction is called out inline wherever it
matters, per Rules.md #5's standard of honest reporting over confident-
sounding but unverified numbers.

---

## Part A — Research findings

### 1. Income and spending distributions

**Income distribution shape.** The empirical literature on personal/
household income broadly agrees on a two-piece shape: the bulk of the
population (roughly the bottom 97-99%) is reasonably well approximated by
a log-normal distribution, while the top 1-3% (high earners) follows a
Pareto (power-law) tail instead — the log-normal underestimates how heavy
that tail actually is. This is a long-standing finding going back to
Aitchison & Brown's *The Lognormal Distribution* (1957) — already this
project's cited source for the log-normal *shape* choice — and is echoed
in more recent work explicitly combining the two (the "double
Pareto-lognormal" distribution; see Reed & Jorgensen and related
literature cited in the general modeling literature on income
distributions).
Source: general finding cross-referenced across [Household Income
Distribution in the USA (arXiv:1602.06234)](https://arxiv.org/pdf/1602.06234),
[Pareto–lognormal distributions: Inequality, poverty, and estimation from
grouped income data (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0264999313001880),
and [Statistical Literacy and the Lognormal Distribution, Schield
2018](http://www.statlit.org/pdf/2018-Schield-ASA.pdf). *(The arXiv PDF
itself could not be text-extracted by this session's tooling — see the
methodological caveat above; this specific claim is corroborated
independently across three separate sources' summaries, which is why it's
reported with more confidence than a single-source claim below.)*

**How this maps onto the simulation**: `world/engine.py`'s
`INCOME_LOGNORMAL_MU`/`INCOME_LOGNORMAL_SIGMA` already use a log-normal —
this is a real, if imperfect, empirical match for the *shape* of most of
a population's income, and the existing code comment already says so
correctly. What the current code does NOT capture, and what the research
above adds a genuinely new caveat about: real income distributions are
NOT log-normal in the tail — the simulation's hard-clamped
`INCOME_MAX = 25000.0` actually sidesteps this by construction (it
prevents the log-normal's under-fat tail from mattering, since nothing
can exceed the cap anyway), which is an honest, if accidental, way the
simplification avoids its main known flaw. This is reported as a genuine
finding, not acted on: capping is already the practical fix a Pareto tail
would have motivated, so no code change follows from this item.

**A specific sigma value found, and why it was NOT used to change the
code.** One search turned up a claim, attributed to labor-economics
literature (via a wage-inequality paper's abstract summary — NBER Working
Paper w28375, "Labor Market Institutions and the Distribution of Wages"),
that "the average standard deviation of log wages within states is close
to 0.5" using U.S. Current Population Survey data. This would coincide
almost exactly with this simulation's existing `INCOME_LOGNORMAL_SIGMA =
0.5`. **This was deliberately NOT used to upgrade the code's provenance
label**, for two honest reasons: (1) the NBER PDF could not be
independently re-verified by this session's tooling (see the
methodological caveat above) — the 0.5 figure is a WebSearch-synthesized
paraphrase of a paper this session never actually read in full, not a
firsthand-verified quote; (2) even if verified, that estimate is for
*wage* dispersion (hourly earnings for employed workers), not *income*
including all sources across an entire adult population (which is wider,
since it includes zero/near-zero earners, retirees, and top-end
non-wage income) — a real but non-trivial mapping gap. Reporting this
honestly (a suggestive, uncomfortably-close-but-unverified number) rather
than quietly adopting it is exactly the standard Rules.md #5 asks for.

**Spending as a fraction of income.** The U.S. Bureau of Labor
Statistics' Consumer Expenditure Survey (CE) is the standard public
source. For 2024: average annual expenditures across all consumer units
were $78,535 against average income before taxes of $104,207 — an
overall spend/income ratio of about 75%. Critically, this ratio is **not
flat across income levels**: BLS's quintile breakdowns and Federal
Reserve commentary consistently show spending as a share of income
falling as income rises (a declining marginal/average propensity to
consume) — lower-income consumer units routinely spend a share of income
at or above 100% (dissaving/credit-financed), while higher-income units
save a much larger share. The Philadelphia Fed's ["Evidence of Diverging
Spending Behavior by Income"](https://www.philadelphiafed.org/-/media/FRBP/Assets/Consumer-Finance/Briefs/Evidence-of-Diverging-Spending-Behavior.pdf)
and the Dallas Fed's ["Consumption concentration may be up, adding
slightly to economic fragility"](https://www.dallasfed.org/research/economics/2025/1125-yang-consume)
both discuss this pattern directly; BLS's own tables (2024 release:
[Consumer Expenditures — 2024](https://www.bls.gov/news.release/pdf/cesan.pdf),
[BLS CE tables index](https://www.bls.gov/cex/tables.htm)) provide the
underlying quintile figures.
Sources: [BLS Consumer Expenditures news release,
2024](https://www.bls.gov/news.release/cesan.nr0.htm); [Philadelphia Fed,
"Evidence of Diverging Spending Behavior by
Income"](https://www.philadelphiafed.org/-/media/FRBP/Assets/Consumer-Finance/Briefs/Evidence-of-Diverging-Spending-Behavior.pdf);
[Dallas Fed, "Consumption concentration may be up, adding slightly to
economic fragility", Nov
2025](https://www.dallasfed.org/research/economics/2025/1125-yang-consume).

**How this maps onto the simulation, and why nothing was changed here
either**: `world/agents/person.py`'s `purchase_amount()` draws a
purchase as a fraction of the *buyer's own* `income_monthly` — the same
fractional range (0.5%-12% per attempt, jittered) regardless of whether
that person is high- or low-income. Real data says the relationship
should go the other way for the aggregate spend/income *ratio*: poorer
people spend a *larger* share of income, not the same share. This is a
genuine, well-supported empirical finding this simulation's current
mechanics do not capture — but fixing it honestly would mean making
purchase-amount-as-a-fraction-of-income itself a function of income level
(a new behavioral mechanism), not swapping a single constant for another
constant, which is outside this task's explicitly narrow Part B scope
("only for parameters that ALREADY exist... a clean, well-supported real-
world number or range"). Recorded here as an honest, actionable finding
for a future, properly-scoped Phase 3 continuation, not acted on now.

---

### 2. Payment/transaction fraud

**Fraud rate, in basis points of transaction value.** The Federal Reserve
Bank of Kansas City's payments-system research briefing (Feb 25, 2026),
drawing on Federal Reserve Board Regulation II debit-card issuer data
(collected under the Dodd-Frank Act's biennial reporting requirement),
reports:
- **Overall fraud losses (2023)**: 17.6 basis points of transaction
  value (i.e. $17.63 lost per $10,000 transacted), up steadily from 7.8
  basis points in 2011 — fraud loss rates have **more than doubled** over
  roughly a decade.
- **Card-present fraud (2023)**: 14.2 basis points for "dual-message"
  (credit-card-style, signature/EMV) networks vs. 5.1 basis points for
  "single-message" (PIN-debit-style) networks — nearly a 3x difference by
  network type.
- **International comparison (card-present, 2023)**: Australia 1.0 basis
  points, EEA (Europe) 0.7 basis points — both far below either U.S.
  network type, consistent with well-known international commentary that
  the U.S.'s slower EMV-chip rollout left it with comparatively higher
  card-present fraud for years.
- **Card-not-present (CNP) fraud** is higher still and has been rising
  faster than card-present fraud as chip adoption pushed fraud toward
  online/remote channels — the same briefing notes single-message CNP
  fraud rates surpassed dual-message CNP rates for the first time in
  2023.

Source: [Federal Reserve Bank of Kansas City, "New Data on Card-Present
and Card-Not-Present Fraud Rates in the United States", Feb 25,
2026](https://www.kansascityfed.org/research/payments-system-research-briefings/new-data-on-card-present-and-card-not-present-fraud-rates-in-the-united-states/)
(fetched directly; figures independently confirmed in the page text, not
just a search snippet).

**Factors correlated with fraud risk, per the academic/applied
literature.** No single number here, but a consistent qualitative
picture across multiple sources:
- **Transaction amount**: fraud detection literature repeatedly treats
  transaction amount as a core feature — both because large transactions
  are attractive targets and because amount, combined with a customer's
  typical spending pattern, is itself a signal (an amount far outside a
  cardholder's normal range is suspicious regardless of its absolute
  size).
- **Velocity/frequency**: rapid repeated transactions (multiple charges
  in a short window, especially across different merchants) are one of
  the most consistently cited fraud signals in applied fraud-detection
  systems and research datasets.
- **Merchant category**: fraud/rapid-transaction rates are reported to
  vary meaningfully by merchant category (small-ticket, high-frequency
  categories showing elevated anomalous-activity rates in some applied
  studies).
- **Account age / geographic-behavioral anomaly**: cited as standard
  features in both the academic literature (Dal Pozzolo et al.,
  "Credit card fraud detection: a realistic modeling and a novel
  learning strategy", IEEE TNNLS 2017/2018; Bhattacharyya, Jha,
  Tharakunnel & Westland, "Data mining for credit card fraud: A
  comparative study", *Decision Support Systems*, 2011) and in applied
  fraud-scoring systems (IP/geography mismatch, distance-from-home,
  new/young account flags).

Sources: [Kansas City Fed briefing (above)](https://www.kansascityfed.org/research/payments-system-research-briefings/new-data-on-card-present-and-card-not-present-fraud-rates-in-the-united-states/);
Bhattacharyya, S., Jha, S., Tharakunnel, K., & Westland, J.C. (2011),
"Data mining for credit card fraud: A comparative study", *Decision
Support Systems* 50(3); Dal Pozzolo, A., Boracchi, G., Caelen, O.,
Alippi, C., & Bontempi, G. (2017/2018), "Credit Card Fraud Detection: A
Realistic Modeling and a Novel Learning Strategy", *IEEE Transactions on
Neural Networks and Learning Systems*. *(These two academic citations
were located and their existence/content confirmed via WebSearch's
summaries and secondary references, not a firsthand full-text read of
the papers — flagged per the methodological caveat above; the specific
factor list is corroborated across multiple independent secondary
descriptions of both papers, which is why it's reported with reasonable
confidence despite not being a direct quote.)*

**Detection / false-positive tradeoffs.** Reported false-positive rates
in recent ML-based fraud-detection research vary enormously by paper and
dataset (some report false-positive rates as low as ~5×10⁻⁵ on curated,
heavily-preprocessed benchmark datasets such as the well-known Kaggle
"Credit Card Fraud Detection" dataset). This project treats these
specific numbers as **not usable** for anything beyond noting that a
detection/false-positive tradeoff exists in the literature — benchmark
datasets are known to be unrepresentative of real-world class imbalance
and concept drift (a point Dal Pozzolo et al. make explicitly), so
quoting a specific false-positive rate as if it generalizes would be
exactly the kind of overclaiming Rules.md #5 warns against.

---

### 3. Credit scoring / creditworthiness dynamics

**Score distribution (a real, if dated, public baseline).** The Federal
Reserve Board's 2007 *Report to Congress on Credit Scoring and Its
Effects on the Availability and Affordability of Credit* (mandated by the
Fair and Accurate Credit Transactions Act of 2003) published a national
FICO-score distribution: roughly 2% of scored consumers below 499, 5%
in 500-549, 8% in 550-599, 12% in 600-649, 15% in 650-699, 18% in
700-749, 27% in 750-799, and 13% at 800+ — a distribution that is
noticeably left-skewed toward the high end (most people cluster in the
650-799 range), not remotely uniform or normal.
Source: [Federal Reserve Board, *Report to Congress on Credit Scoring*,
2007](https://www.federalreserve.gov/boarddocs/RptCongress/creditscore/general_tables.htm).
**Honest caveat: this is 2007 data**, nearly two decades old, and the
report itself is proprietary-FICO-adjacent (the task brief explicitly
asked to avoid "proprietary FICO internals" — this report is the
Fed's own public regulatory analysis of that data, not FICO's own
methodology, so it's used here only as a distributional shape reference,
not a scoring-formula reference). A materially more current, free, public
score-distribution breakdown was not found in this session's search
budget — reported as a real gap, not papered over.

**Score/delinquency *transition* dynamics — the closer, more current
match.** The New York Fed's Center for Microeconomic Data publishes a
quarterly *Household Debt and Credit Report*, drawing on the FRBNY
Consumer Credit Panel / Equifax data, including a "transition into
serious delinquency" (90+ days late) series by debt type. The Q1 2026
report (published May 12, 2026) gives, as a share of balances flowing
into 90+-day delinquency: mortgages 1.48% (up from 1.22% in Q1 2025),
HELOC 1.15% (up from 0.88%), auto loans 2.97% (up from 2.94%), credit
cards 7.10% (up from 7.04%), overall across all debt types 2.83% (up
from 2.45%). Early-delinquency transition rates were also reported:
credit cards 8.6% annually (down slightly from 8.7%), mortgages 3.8%
(down from 3.9%). The report also notes a **methodology change**: the
series switched from Equifax Risk Score 3.0 to VantageScore 4.0 starting
2026:Q1 — both range 300-850 and are described as similarly distributed
in purpose, but this is exactly the kind of "the label changed under the
data" fact worth recording rather than silently assuming continuity.
Source: [Federal Reserve Bank of New York, "Household Debt Balances Rise
Slightly as Delinquency Transition Rates Hold Steady", May 12,
2026](https://www.newyorkfed.org/newsevents/news/research/2026/20260512)
(fetched directly).

**How this maps onto the simulation**: this project has no credit-score
or delinquency-transition mechanism at all yet (Part C below proposes
one). These are the two most directly reusable real numbers for that
future design: a real published transition-into-90+-day-delinquency rate
by debt type (0.9-7.1% depending on debt type, per year) and a real
(if dated) baseline score-distribution shape to seed a synthetic score at
population-generation time.

---

### 4. Loan interest rate mechanics

**Spread-over-benchmark mechanics.** The Federal Reserve's own FEDS Notes
research (Sept 24, 2025) directly studies how lenders price credit risk
into loan rates, benchmarked against a base rate (10-year Treasury for
mortgages, prime rate for credit cards): a 100-basis-point increase in
regional default risk is associated with roughly a 30-basis-point
increase in jumbo mortgage rates, but only about a 5-basis-point increase
in credit-card APRs — i.e. **risk is priced into the rate, but the
"spread per unit of risk" differs a lot by loan type**, and even after
controlling for risk, a large share of rate variation remains
unexplained (attributed to market power/lending-cost factors the note
does not fully quantify). Separately, a 1% increase in a bank's average
net charge-offs was associated with roughly a 0.6% increase in its
average interest-and-fee income across the 2008-2019 cycle, at the
bank-portfolio level, not the individual-loan level.
Source: [Federal Reserve, FEDS Notes, "Examining the Relationship Between
Loan Pricing and Credit Risk", Sept 24,
2025](https://www.federalreserve.gov/econres/notes/feds-notes/examining-the-relationship-between-loan-pricing-and-credit-risk-20250924.html)
(fetched directly).

**Actual rate levels.** The Fed's G.19 Consumer Credit release tracks the
finance rate on 24-month personal loans at commercial banks
(`TERMCBPER24NS`) back to 1972: historical range roughly 8.73% (record
low, May 2022) to 19.21% (record high, November 1981); most recently
reported at 11.65% (November 2025). This is an aggregate "most common
rate," not a risk-tiered schedule — it does not by itself show the
spread *between* a low-risk and high-risk borrower, only the level over
time (which correlates loosely with the general interest-rate
environment, e.g. Fed funds rate cycles).
Source: [FRED, "Finance Rate on Personal Loans at Commercial Banks, 24
Month Loan"](https://fred.stlouisfed.org/series/TERMCBPER24NS).

**Default/delinquency ranges for unsecured consumer credit.** From the
same FRBNY Q1 2026 report cited above: credit-card 90+-day delinquency
transition rate 7.10% (the highest of any debt type reported, consistent
with unsecured credit card debt being priced/underwritten as higher-risk
than secured debt like mortgages/auto). Historical Fed Bulletin data
(1990s-2000s) put credit-card *delinquency rates* (not just transitions)
in a roughly 2.6%-5.5% range across the last three decades' full credit
cycles (a 2008-crisis peak just above 5.5% delinquency / just above 6%
net charge-off; more recent 2024 cycle peak 3.2% delinquency / 4.6%
charge-off; pre-pandemic baseline roughly 2.6% delinquency / 3.7%
charge-off).
Sources: [FRBNY Q1 2026 Household Debt and Credit Report (above)](https://www.newyorkfed.org/newsevents/news/research/2026/20260512);
Federal Reserve Bulletin historical bank-profitability series (2007-2009
volumes, `federalreserve.gov/pubs/bulletin`).

**How this maps onto the simulation**: no loan/interest mechanism exists
yet (Part C proposes one). The reusable numbers: risk-based rate spreads
are real but loan-type-specific and only partially explained by
measurable default risk (5-30bps per 100bps of regional default risk,
depending on loan type); unsecured consumer credit (the loan type most
analogous to anything this simulation's Person agents might plausibly
need) delinquency/transition rates cluster in roughly a 2.6%-8.6% band
depending on exactly which statistic (delinquency vs. transition-into-
delinquency vs. charge-off) and which point in the credit cycle.

---

### 5. Bank reserve/liquidity behavior

**Public regulatory description.** The Federal Reserve's own reserve-
requirements page confirms the general mechanism this project's
`bank_reserve` asset account is already loosely modeled on: historically,
reserve requirements obligated depository institutions to hold a
specified fraction of certain deposit types as vault cash or as balances
at the Fed, on a tiered schedule (0% for smaller deposit tranches, 3%
and 10% for larger tranches, indexed annually). Critically: **as of March
26, 2020, the Federal Reserve Board reduced all reserve requirement
ratios to zero percent**, eliminating reserve requirements for all U.S.
depository institutions — this is current, standing policy, not a
temporary pandemic-era footnote that later reversed. Reserve behavior
today is governed by banks' own liquidity/capital management and other
post-2008 regulatory tools (e.g. the Liquidity Coverage Ratio), not a
binding statutory reserve ratio.
Source: [Federal Reserve Board, "Reserve
Requirements"](https://www.federalreserve.gov/monetarypolicy/reservereq.htm)
(fetched directly, official/current page).

**How this maps onto the simulation**: `world/agents/bank.py`'s
`bank_reserve` account is explicitly documented (see that module's
docstring) as representing "cumulative external cash [the bank] has
received on behalf of its depositors" — i.e. it functions as an asset-
side balancing entry for the double-entry ledger, not as a regulatory
minimum-reserve constraint on lending. This research finding is honestly
reported as **not requiring any code change**: (1) there's no lending
mechanism yet for a reserve *requirement* to meaningfully constrain (no
loans exist to be capital-constrained against, per Part C), and (2) the
real-world fact that the U.S. has had a literal 0% reserve requirement
since 2020 actually means a hard reserve-ratio *constraint* would be the
less realistic choice for a present-day-set simulation, not the more
realistic one — the current unconstrained, monotonically-non-decreasing
reserve account is, if anything, closer to 2020s reality than a
classical fractional-reserve constraint would be. Recorded for Part C's
future loan-mechanism design (where actual capital-adequacy-style
constraints, if ever added, should reference Basel/LCR-style regulatory
capital concepts rather than a pre-2020 reserve-ratio model).

---

## Part B — What was (and wasn't) changed in code, and why

Per the task brief: code changes are authorized **only** for parameters
that already exist in the running simulation (income distribution
shape/params, base spend probability, opening-balance fraction,
settlement timing), and only where research turned up something clean
and well-supported enough to justify it — not speculatively.

### Changed: settlement-delay provenance (not the value)

**File**: `Simulation/world/engine.py`, `SimulationEngine._run_settlement`
docstring.

**Before**: labeled purely "MODELING ASSUMPTION," stating T+1 was "a
simple named stand-in for real card-network settlement cycles (commonly
on the order of 1-2 business days), not calibrated to any specific
processor or network."

**After**: relabeled "RESEARCH-GROUNDED, WITH A NAMED SIMPLIFICATION."
The fact that real card-network settlement takes on the order of one to
several business days (not instant) is now backed by a direct citation —
Stripe's own public documentation, fetched directly: "settlement
typically takes one to three business days after the transaction," for
card payments (Stripe, "Payment settlement explained: how it works and
how long it takes",
stripe.com/resources/more/payment-settlement-explained-how-it-works-and-how-long-it-takes),
independently corroborated by other payments-industry processor
explainers reporting the same 1-3 business day window (e.g. Clearly
Payments, "How Long Do Credit Card Payments Take to Settle?"). The docstring
is explicit that this only grounds the *qualitative* fact (settlement is
genuinely delayed, on a roughly 1-3 business day scale) — the *specific*
choice of exactly T+1, applied uniformly with zero variation, remains a
named modeling simplification, since no source claims every merchant
settles in exactly one day, and this simulation doesn't model the
network/risk-tier/country variables that would place a given merchant
anywhere in that real 1-3 day range.

**Value unchanged.** T+1 was kept as-is (not widened to a random 1-3 day
draw), for two reasons stated plainly in the new docstring: (1) T+1
already sits inside the real, cited range (at its low/most-conservative
end), so there was no research-driven reason to move it; (2) making
settlement delay itself an RNG draw would perturb the RNG draw sequence
for purchases/salary, which Phase 2 deliberately avoided disturbing (see
Memory.md's Phase 2 section) — a structural change this one citation does
not by itself justify. This is a provenance-only change: no output number
this simulation produces is different because of it (verified — see
Testing below).

### Deliberately NOT changed, and why (per parameter)

- **Income distribution shape/params** (`INCOME_LOGNORMAL_MU`/`_SIGMA` in
  `world/engine.py`): the log-normal *shape* is already about as well
  supported as this literature gets for the bulk of a population — no
  change needed there. The one specific number found that might have
  looked temptingly close (`sigma≈0.5` from a wage-inequality paper
  summary) was deliberately not adopted: it could not be independently
  verified against the primary source in this session (PDF-extraction
  tooling limitation, see the methodological caveat), and "wage
  dispersion among employed workers" is not quite the same population as
  "all persons' income" this simulation models. Adopting an unverified,
  imperfectly-mapped number just because it happened to match the
  existing constant would be exactly the kind of false-authority Rules.md
  #2 exists to prevent. `INCOME_MIN`/`INCOME_MAX` also have no clean
  real-world anchor since the simulation's income unit isn't tied to any
  real currency/scale (a fact the existing code comment already states
  correctly) — there's no honest way to "calibrate" an absolute income
  level to USD Census figures without implicitly picking a currency scale
  nobody asked this project to commit to.
- **Base daily spend probability** (`BASE_DAILY_SPEND_PROB = 0.35` in
  `world/agents/person.py`): the Federal Reserve's Diary of Consumer
  Payment Choice (an annual, well-established public survey) was the
  most promising lead — search results referenced a reported statistic
  that roughly half of consumers make zero payments on a given diary day
  (implying ~50% "at least one payment today," which would suggest a
  meaningfully higher base rate than 0.35). **This was not adopted**,
  for two honest reasons: (1) this session's WebFetch could not
  successfully retrieve or verify that number against any primary DCPC
  report PDF or HTML page despite several attempts (all DCPC PDFs
  returned unparseable binary content, and no HTML page found stated the
  figure directly) — it exists only as an unverified WebSearch synthesis,
  which is too thin to act on for a code change (documented as thin per
  Rules.md #5, not treated as a citation); (2) even if verified, DCPC
  counts ALL payments (bills, rent, transfers, recurring debits), while
  `BASE_DAILY_SPEND_PROB` specifically models a *discretionary* purchase
  attempt — a materially narrower category than "any payment," so the
  two numbers aren't measuring the same thing even setting aside the
  verification problem. Recorded as a real, worth-revisiting lead for a
  future session with better PDF-extraction tooling, not acted on now.
- **Opening balance fraction** (`OPENING_BALANCE_FRACTION_RANGE = (0.1,
  1.0)` in `world/engine.py`): the Fed's Report on the Economic
  Well-Being of U.S. Households (SHED survey) gives real, relevant, and
  directly-fetched figures (63% of adults could cover a $400 emergency
  expense with cash/equivalent; 55% report having a 3-month emergency
  fund) that are broadly *consistent* with the current uniform
  10%-100%-of-monthly-income range (a population where roughly half have
  multi-month buffers and a meaningful minority are near the low end is
  compatible with a wide uniform spread) — but these are point-in-time
  adequacy statistics, not a distributional shape or range for "opening
  balance as a fraction of monthly income," so there's no clean number to
  substitute in for the uniform range itself. Left unchanged; the
  consistency is reported as a mild positive sanity check, not a
  citation-backed replacement.

---

## Part C — Proposed future mechanisms (NOT implemented)

These are Phase 3+/4/Beyond-Phase-6 territory per Phases.md, explicitly
not built here. Each is written up at a design level: new agent state,
event-generation logic (grounded in Part A's findings, with specifics
cited rather than hand-waved), explicit per-rule provenance labeling
(Rules.md #2), and why it's being proposed rather than built now.

### C.1 — Payment fraud

**New agent/data-model state needed**:
- `Person`: a hidden `fraud_propensity` trait (not visible to any
  decision logic the way `risk_preference` is, otherwise it would leak
  into spend-probability decisions and defeat the point of a fraud
  signal being *detectable from behavior*, not given away for free) —
  MODELING ASSUMPTION for its existence/shape (there is no cited
  distribution for "how fraud-prone is a given person," because fraud is
  mostly not initiated by the legitimate account holder in the first
  place — see below).
- A new, distinct concept: **compromise events** — a Person's account
  becomes "compromised" at some point (card skimmed, credentials
  phished, etc.), which is the actual mechanism that produces fraud in
  the real world far more often than a legitimate account holder
  defrauding their own account. This needs new `Transaction.kind` values
  (`fraud_attempt`, maybe `fraud_blocked` vs. `fraud_succeeded`) and a
  new boolean/flag on `Transaction` (`is_fraudulent`) distinguishing a
  fraud transaction from an ordinary `purchase`/`payment_failure`.
- `Merchant`: a `category`-linked risk multiplier (the `MERCHANT_CATEGORIES`
  field already exists as a cosmetic placeholder per Phase 1's Memory.md
  — this would be the first mechanism that actually uses it
  behaviorally).

**Event-generation logic, grounded in Part A findings**:
1. Each day, a small, low, per-account probability of a "compromise
   event" starting (PLACEHOLDER — no source found gives a real per-
   account-per-day compromise probability; this would need to be picked
   and explicitly marked as a placeholder pending better data, not
   invented and presented as calibrated).
2. Once compromised, generate a burst of `fraud_attempt` transactions
   at elevated **velocity** (multiple attempts in a short window) and
   at **amount** patterns skewed away from that person's own historical
   normal range — both are the two most consistently cited fraud
   signals in the literature (Bhattacharyya et al. 2011; Dal Pozzolo et
   al. 2017/2018; Part A §2 above). RESEARCH-GROUNDED for the *signal
   choice* (velocity + amount-anomaly are real, well-cited features),
   MODELING ASSUMPTION for the exact functional form connecting
   "compromised" to a specific attempt-rate/amount-distribution (no
   source gives that specific curve).
3. Overall fraud rate, once implemented, should be checkable against the
   real, well-sourced target: **~17.6 basis points of transaction value**
   for 2023 (Kansas City Fed, Part A §2) as the calibration target for
   "does this mechanism produce a realistic overall fraud rate," with
   the historical trend (7.8bps in 2011 → 17.6bps in 2023) available as
   a secondary check if a time-varying rate is ever wanted. This is
   genuinely the single cleanest calibration target in all of Part A —
   a specific, well-sourced, directly-comparable number a fraud mechanism
   could be checked against.
4. A `fraud_attempt` should be probabilistically caught/blocked before
   completing (mirroring real detection systems) — but Part A's search
   for a real, generalizable false-positive/detection-rate number came
   up thin (benchmark-dataset numbers like 5×10⁻⁵ false-positive rates
   are explicitly flagged in the literature itself as unrepresentative
   of production conditions — see Part A §2's honest caveat). Any
   detection-probability constant here would have to be a labeled
   PLACEHOLDER, not dressed up as research-grounded.

**Why not built now**: this needs a genuinely new causal object (account
compromise, not just an existing Person's own decision) that doesn't fit
Architecture.md's existing "every agent decision is a function of that
agent's own visible state" model cleanly — fraud is, definitionally,
*not* the account owner's decision, so it needs either a new synthetic
attacker "agent" or a special-cased event generator, either of which is
a real design decision this task's narrow scope explicitly reserves for
a dedicated, reviewed Phase 4-class effort (Phases.md: "Payment retries,
refunds... generated causally from agent state" is the closest existing
authorized scope, and fraud is a materially different, riskier addition
than that).

### C.2 — Credit scoring

**New agent/data-model state needed**:
- `Person`: a new `credit_score` field (300-850 range, matching both
  FICO and VantageScore 4.0's stated ranges per Part A §3), initialized
  at world-generation time from a distribution seeded by the 2007 Fed
  Report to Congress's published national distribution (Part A §3) —
  RESEARCH-GROUNDED for the *initial* distribution shape, with the
  honest caveat that it's 2007 data (no cleaner, current, free public
  breakdown was found — see Part A §3).
- A new `CreditEvent` or extension to `Event` capturing what changed a
  score and by how much, so score changes stay causally traceable
  (matching this project's whole reason for existing — PRD.md's "Why").

**Event-generation logic, grounded in Part A findings**:
1. Score should move (mostly downward, in small increments) in response
   to a Person's own `payment_failure` transactions — this is the
   direct, natural causal link this simulation is uniquely positioned to
   produce honestly (a score drops *because* a specific agent had a
   specific traceable failed payment, not from an off-model coin flip).
   MODELING ASSUMPTION for the exact magnitude of each score movement (no
   source gives a "score points lost per missed payment" figure suitable
   for citation — score-formula internals are proprietary, which is
   exactly why the task brief said to avoid FICO internals).
2. A *rate* target this mechanism could be checked against does exist,
   from FRBNY's Q1 2026 transition data (Part A §3): roughly 7.10% of
   credit-card balances transition into 90+-day serious delinquency in a
   given period, vs. 1.48% for mortgages and 2.97% for auto — i.e.
   whatever the eventual person-level delinquency mechanism produces in
   aggregate, per-debt-type transition rates in the 1-8% range (not
   flat, and not uniform across debt/product type) is the real,
   cited target shape. RESEARCH-GROUNDED for this aggregate check.
3. Score recovery over time (for a Person with a clean payment record)
   would need its own rate — Part A's search did not turn up a clean,
   generalizable "recovery half-life" statistic (proprietary scoring
   internals again), so this would have to be a named PLACEHOLDER.

**Why not built now**: needs a genuinely new piece of *persistent* agent
state that (unlike balance) doesn't reset/reconcile against any ledger —
there's no natural "debit/credit" pair for a credit-score change the way
Phase 2's double-entry model requires for money movements, so it would be
the first agent field in this codebase that lives entirely outside the
ledger-invariant discipline Phase 2 established. That's a real
architectural decision (does it need its own audit trail? does it get
its own "ledger" analog for auditability?) worth a dedicated review, not
something to bolt on inside a narrow research task.

### C.3 — Loan / interest mechanics

**New agent/data-model state needed**:
- A new `Loan` dataclass: `loan_id`, `person_id`, `principal`,
  `interest_rate`, `origination_day`, `term_days`, `outstanding_balance`,
  `status` (current/delinquent/defaulted/paid-off).
- `Bank`: a loans registry parallel to the existing `accounts` dict, plus
  (if this is ever built) a real "loanable funds" constraint — Part A §5
  found that a classical fractional-reserve constraint would actually be
  *less* realistic for a present-day simulation than an unconstrained
  model (U.S. reserve requirements have been 0% since March 2020), so
  any capital constraint added here should be modeled on Basel-style
  capital-adequacy/Liquidity-Coverage-Ratio concepts, not a pre-2020
  reserve-ratio model — an explicit, cited correction to what a naive
  "add bank reserve requirements" design might otherwise assume.

**Event-generation logic, grounded in Part A findings**:
1. `interest_rate = base_rate + risk_spread(person)`, where `risk_spread`
   is a function of the borrower's (proposed, from C.2)
   `credit_score` — RESEARCH-GROUNDED for the *structure* (rate = base +
   risk-based spread is exactly how the Fed's own Sept 2025 FEDS Note
   (Part A §4) describes real consumer lending), with the specific
   *elasticity* citable per loan type: roughly 5 basis points of APR
   spread per 100 basis points of regional default risk for
   credit-card-type unsecured credit (vs. ~30bps for mortgages) — the
   closest thing in all of Part A to a real, quantified spread-per-risk-
   unit number, though it's a regional-default-risk elasticity, not a
   per-individual-credit-score elasticity, so translating it into a
   per-person spread function would still involve a MODELING ASSUMPTION
   step.
2. `base_rate` itself could be checked against G.19's real historical
   range for 24-month personal loans (8.73%-19.21%, Part A §4) as a
   plausibility bound for whatever base rate this simulation picks —
   RESEARCH-GROUNDED as a sanity-check range, not as a specific value
   (the simulation has no real-world-mapped time axis to place itself on
   that 1972-2025 series).
3. Default/delinquency probability, if a Loan's `status` transitions
   probabilistically, has real target ranges from Part A §4: card-type
   unsecured credit delinquency has historically ranged roughly 2.6%-5.5%
   across full credit cycles (with a corresponding charge-off range of
   roughly 3.7%-6.2%) — RESEARCH-GROUNDED as an aggregate-rate target,
   same caveat as C.2's item 2 about not specifying individual-level
   functional form.

**Why not built now**: this is the largest of the three proposals —
it needs a new persistent liability-side object (`Loan`) that interacts
with the existing double-entry ledger in a way Phase 2 never designed
for (a loan disbursement is a *new* money-creation event from the bank's
perspective, conceptually different from `fund_external`'s "external
source, e.g. salary" pattern — modeling it honestly means deciding
whether/how a Bank's lending capacity is itself constrained, which C.3's
own research finding above shows the "obvious" naive answer (reserve
ratio) would be factually backwards for a present-day setting). This is
exactly the kind of undertaking Phases.md's Beyond-Phase-6 list already
flags as "independently a Phase-1-sized undertaking in its own right" —
building it hastily inside a narrow research task risks breaking the
currently-passing, fully-tested double-entry invariant this project's
last two phases spent real effort establishing.

---

## What was not downloaded, and why

No dataset was bulk-downloaded. Every finding above is either a cited
summary statistic already published in a report/press release (Kansas
City Fed, FRBNY, BLS, Federal Reserve Board FEDS Notes, FRED series
pages), or an academic paper's reported finding (cited by title/author/
year, per Rules.md #2's citation standard) accessed via WebSearch/
WebFetch against the publisher's own page — never a raw microdata file.
The FRBNY Consumer Credit Panel, BLS CE public-use microdata, and DCPC
day-level datasets (all mentioned in search results as available for
direct download) were deliberately NOT fetched: this task's own
brief explicitly says "prefer citing a paper's/report's own published
summary statistics over bulk-downloading large raw datasets," and every
number needed for this document was obtainable from a published summary
without touching raw microdata. Nothing gated, paid, or login-required
was accessed.

## Honest overall summary

Part A's research is real, dated, sourced, and — for fraud rates,
delinquency transition rates, and loan-pricing mechanics — good enough to
directly inform Part C's future-mechanism designs with genuine numbers,
not invented ones. Part B's actual code footprint is intentionally small
(one provenance-upgrade docstring, zero constant-value changes, zero
behavioral changes) because, on close inspection, none of the four
eligible existing parameters had a research finding that was BOTH clean
AND cleanly mapped onto exactly what that parameter models — several
looked tempting (the sigma≈0.5 coincidence, the DCPC zero-payment-day
statistic) and were deliberately not used because they failed
verification or definitional-match tests, not because no research was
found. That is itself the correct Phase 3 outcome per this project's own
stated standard (Rules.md #5): a small, honestly-reported result, not an
inflated one.
