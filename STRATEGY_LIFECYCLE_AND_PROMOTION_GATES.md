# Strategy Lifecycle and Promotion Gates

## 1. Lifecycle states

Every strategy version must have one explicit state:

1.  `DRAFT` --- hypothesis recorded; not yet tested.
2.  `RESEARCH` --- undergoing exploratory development.
3.  `BACKTESTED` --- historical simulation completed; not necessarily
    passed.
4.  `VALIDATION` --- undergoing chronological validation and robustness
    testing.
5.  `QUALIFIED_CANDIDATE` --- passed predeclared historical gates.
6.  `FROZEN_PAPER` --- immutable candidate undergoing live paper
    evaluation.
7.  `PAPER_PASSED` --- passed the predeclared paper evaluation.
8.  `DEMO_REVIEW` --- eligible for exchange demo integration review.
9.  `REJECTED` --- failed one or more mandatory gates.
10. `RETIRED` --- no longer considered active.

A state change must be recorded with timestamp, actor, reason, and
evidence reference.

## 2. Version identity

A strategy version must identify: - strategy family; - semantic version
or unique immutable ID; - code commit; - configuration checksum; -
feature definitions; - risk profile; - execution model assumptions.

Never reuse a version identifier for changed behavior.

Example: - `trend_momentum-v1.0.0` --- existing failed baseline. -
`trend_momentum-v1.1.0` --- a new candidate with a documented change.

These are naming examples only.

## 3. Gate A --- Data and implementation integrity

Must pass: - data-quality audit; - timestamp and candle-close checks; -
no-lookahead tests; - deterministic replay where expected; - correct fee
and spread application; - correct order sizing and rounding; - correct
position and cash accounting; - no duplicate order behavior; - critical
tests pass.

Failure means no performance verdict can be trusted.

## 4. Gate B --- Historical performance

Predeclare thresholds before viewing final test results.

Minimum principles: - positive net expectancy on out-of-sample data; -
profit factor greater than 1 after costs; - drawdown within
owner-approved risk limit; - no single trade or narrow interval
dominates results; - adequate trade count for the strategy; - comparison
against buy-and-hold and do-nothing; - costs and slippage modeled
realistically.

Optional stricter target: profit factor above 1.2. This is a proposed
project target, not a universal standard. Owner approval is required
before it becomes binding.

A positive return alone is not enough.

## 5. Gate C --- Robustness

Evaluate: - walk-forward windows; - different market conditions; -
reasonable parameter neighborhoods; - higher costs and execution
delays; - trade-sequence risk; - sensitivity to data boundaries; -
stability of trade frequency and expectancy.

Reject or mark inconclusive if performance depends on a narrow parameter
setting or one exceptional period.

## 6. Gate D --- Candidate approval and freeze

Before live paper evaluation: - select one candidate; - record immutable
version and configuration; - record code commit and dataset
references; - record risk limits and cost assumptions; - define
evaluation start/end and minimum evidence; - define
pass/fail/inconclusive thresholds; - require owner approval.

The research system must not change the frozen candidate.

## 7. Gate E --- Live paper evaluation

Current roadmap minimum: - 30 calendar days; - at least 30 completed
trades; - live market data; - simulated funds; - no strategy-rule
changes during the run.

Interpretation: - This is an initial minimum, not proof of durable
profitability. - If trade count is too low or market conditions are not
sufficiently varied, extend the run. - A strategy change invalidates the
current run; create a new evaluation ID. - Operational defects may
invalidate the run regardless of P&L.

Evaluate net returns, profit factor, drawdown, expectancy, trade
distribution, costs, execution discrepancy, data health, and risk
events.

## 8. Gate F --- Paper result classification

### PASS TO DEMO REVIEW

All predeclared performance and operational criteria pass.

### FAIL

One or more mandatory criteria fail.

### INCONCLUSIVE

Insufficient sample size, market diversity, or evidence.

### OPERATIONAL FAIL

Data, accounting, execution, or reliability defects invalidate the
results.

Do not convert `INCONCLUSIVE` to `PASS` merely because the evaluation
period ended.

## 9. Gate G --- Exchange demo

Demo integration verifies exchange API behavior, not profitability.

Test: - authentication and permission scope; - order creation and
cancellation; - partial fills and rejected orders; - quantity precision
and minimum notional; - reconnect and rate-limit behavior; - restart
recovery; - balance and position reconciliation; - idempotency; -
emergency stop.

Keep demo and live credentials separate. Never grant withdrawal
permissions.

## 10. Live readiness

No automated transition to live trading is permitted.

A separate human-approved checklist must verify: - current platform
access and legal/regulatory suitability; - account and API
permissions; - minimum order constraints; - actual fee schedule; -
secret storage; - monitoring and alerting; - kill switch; - recovery
procedures; - maximum capital at risk; - user understands potential
total loss.

Even after all gates pass, future profitability is not guaranteed.
