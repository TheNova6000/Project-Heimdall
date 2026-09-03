# Financial World Simulation -- Phase 1 Descriptive Statistics

## Volume

- Persons: 25
- Simulated days: 14
- Transactions (total rows): 107
- Events: 107
  - payment_failure: 2 (1.9%)
  - purchase: 98 (91.6%)
  - salary: 7 (6.5%)
- Avg transactions/day: 7.64

## Payment failure rate

- Purchase attempts (purchase + payment_failure): 100
- Failed: 2 (2.00%)
- Succeeded: 98 (98.00%)

## Purchase amount distribution (successful purchases)

- count: 98
- min: 11.81
- p25: 104.77
- median: 189.77
- p75: 304.58
- p95: 712.00
- max: 1,169.46
- mean: 241.59
- stdev: 202.20

## End-of-run Person balance distribution

- min: 166.93
- median: 2,275.82
- max: 6,171.47
- mean: 2,219.51
- balances < 0: 0 (must be 0 -- Rules.md #7)

## Causal-structure check (this project's central question)

PRD.md's hypothesis: a payment should fail *because* the paying agent's own balance was insufficient at that moment, not because an independent per-category probability was drawn (the limitation found in financial_system's generator).

- payment_failure rows where balance_before < amount: 2/2 (OK -- mechanism holds by construction)
  (This is close to tautological by construction -- Bank.debit only ever returns False when balance_before < amount, see world/agents/bank.py -- but it is the direct, inspectable, per-transaction evidence that the failure traces to that specific agent's state at that specific moment, not to a label. The more interesting question is below.)

### Failure rate by income group (below- vs at/above-median income)

- Below-median income (12 persons): 1/52 attempts failed (1.92%)
- At/above-median income (13 persons): 1/48 attempts failed (2.08%)

- Below-median-income failure rate is 0.92x the at/above-median rate.
  If this ratio is meaningfully > 1, failures are concentrating among lower-income (structurally lower-balance-factor) persons, which is the kind of heterogeneous, state-dependent pattern the current financial_system generator's flat per-category rate cannot produce. If it is close to 1, that is also a valid, honestly-reported Phase 1 finding (Rules.md #5, #9).

### Failure rate by balance-to-income ratio at moment of attempt

| balance_before / income_monthly | attempts | failed | failure rate |
|---|---|---|---|
| < 0.02 | 0 | 0 | n/a |
| 0.02 - 0.05 | 0 | 0 | n/a |
| 0.05 - 0.10 | 1 | 0 | 0.00% |
| 0.10 - 0.25 | 7 | 2 | 28.57% |
| >= 0.25 | 92 | 0 | 0.00% |

A monotonically decreasing failure rate down these rows is the clearest evidence that failure is being driven by each agent's own balance state at the moment of the attempt, not by a fixed per-category rate -- this is the structure financial_system's generator lacks (PRD.md 'Why').
