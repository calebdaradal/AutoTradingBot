# Research and Evaluation Plan

## 1. Objective

Establish a repeatable process to research, test, compare, and qualify
intraday trend-momentum strategy candidates before any consideration of
real-money trading.

The purpose is not to maximize a single historical return. The purpose
is to determine whether a candidate has a plausible, repeatable positive
expectancy after realistic costs and within predefined risk limits.

## 2. Fixed project scope

Unless the owner explicitly changes it:

-   BTC/USDT spot.
-   Long-only.
-   15-minute signal/decision timeframe.
-   1-hour trend confirmation.
-   Paper trading only.
-   No leverage, margin, futures, shorting, or borrowed funds.
-   Current baseline: `trend_momentum` v1.0.

Do not convert the project to scalping as part of this plan.

## 3. Current baseline and known result

`trend_momentum` v1.0 is a failed research baseline, not an approved
profitable strategy.

  Period         Strategy return   Buy-and-hold
  ------------ ----------------- --------------
  Train                  -15.20%        -19.48%
  Validation             -12.41%        +33.12%
  Test                    -8.73%        -13.13%
  All                    -15.20%         -6.89%

Reported win rate is 29--41%; profit factor is 0.34--0.50. The strategy
reportedly loses before costs, and six sensitivity variants ended near
-15%.

Preserve the original code/configuration/results so future candidates
can be compared against it.

## 4. Research workflow

### Phase A --- Repository and data audit

Before strategy research:

1.  Verify historical data coverage, intervals, symbol, exchange source,
    and timezone.
2.  Re-run data-quality checks for missing, duplicated, malformed,
    out-of-order, or inconsistent candles.
3.  Verify candle boundary semantics and whether the latest candle is
    closed.
4.  Check that 15-minute and 1-hour series align correctly.
5.  Verify the 1-hour confirmation logic cannot see an unclosed candle.
6.  Check whether historical bid/ask or trade-level data exists. Do not
    assume it does.
7.  Record dataset version, date coverage, row counts, and checksum
    where practical.

**Output:** Data audit report. A reported zero-gap sync is useful but is
not a substitute for validating data correctness and source consistency.

### Phase B --- Market characterization

Characterize the available data before designing filters.

Analyze: - broad directional periods; - trending versus ranging
behavior; - volatility distribution; - volume distribution and unusual
volume; - trend persistence and reversals; - drawdown and rebound
periods; - frequency and magnitude of adverse/favorable price movement
after candidate entries; - time-of-day effects only if the data supports
them and the hypothesis is justified.

Avoid arbitrary market labels. Define regime rules mathematically,
document them, and test whether they are stable.

**Output:** Market characterization report with definitions,
charts/tables, and limitations.

### Phase C --- Strategy hypothesis development

For every proposed change, write a hypothesis before running the
experiment.

A hypothesis must state: - observed weakness in the baseline; - proposed
mechanism for improvement; - exact rule or feature being changed; -
expected measurable effect; - possible downside or trade-off; -
evaluation metrics; - conditions that would falsify the hypothesis.

Examples of experiment families: - trend confirmation; - entry timing; -
volume confirmation; - volatility suitability; - stop placement; -
profit-taking; - time-based exit; - regime filtering.

Do not combine many unrelated changes in one experiment. Use controlled
comparisons where feasible.

### Phase D --- Historical backtesting

Use the existing 180-day history to replay the market chronologically.
This is a computation over stored data; it does not require waiting 180
calendar days.

The backtest must: - make decisions only with information available at
the decision timestamp; - use next-candle or otherwise explicitly
modeled execution timing; - model fees, spread, slippage, order
constraints, and position sizing; - handle stop/target conflicts
conservatively; - include realistic minimum notional and quantity
precision; - track gross and net P&L separately; - compare against
buy-and-hold and do-nothing benchmarks; - report exposure, trade count,
turnover, and holding duration; - preserve the exact assumptions used.

Do not treat candle-based fills as equivalent to real order-book
execution.

### Phase E --- Chronological validation

Use chronological partitions. Do not randomly shuffle time-series
observations.

Recommended protocol: 1. Training period: hypothesis development and
parameter calibration. 2. Validation period: compare candidate versions
and reject weak variants. 3. Final holdout/test period: use sparingly
for final assessment, not repeated tuning. 4. Walk-forward windows:
repeatedly train/calibrate on past data and evaluate on the next unseen
segment.

The exact split dates and proportions must be taken from the current
backtester configuration and recorded. Do not invent or silently change
them.

If 180 days is too little to support enough independent market
environments or walk-forward windows, report that limitation and obtain
more history before claiming robust validation.

### Phase F --- Robustness and stress tests

At minimum, test: - baseline cost assumptions; - higher fee
assumptions; - higher spread and slippage assumptions; - execution
delay; - missed/partial fills if the simulator supports them; -
sensitivity to nearby parameter values; - different chronological
windows; - different market regimes; - losing-trade sequence stress; -
operational faults such as stale data and reconnect/restart.

Monte Carlo: - Resample trade outcomes or trade sequences only with a
clearly stated method. - Preserve relevant dependence where possible;
naive independent shuffling can understate clustered losses. - Report
drawdown and outcome distributions, not a single simulated result. -
Monte Carlo does not create new market evidence; it explores uncertainty
under its assumptions.

### Phase G --- Candidate qualification

A candidate may advance only if all mandatory gates pass:

1.  Data and no-lookahead checks pass.
2.  Net out-of-sample expectancy is positive.
3.  Profit factor is above 1 after costs.
4.  Drawdown is within the owner-approved risk limit.
5.  Performance is not dependent on one trade or one short period.
6.  Results are reasonably stable across walk-forward windows and market
    conditions.
7.  Cost and execution stress tests do not destroy the edge under
    plausible assumptions.
8.  No critical risk, accounting, or operational defects remain.
9.  The complete experiment is reproducible.

Optional initial research targets such as profit factor \> 1.2 may be
considered, but must be explicitly approved and must not be treated as
universal standards. Thresholds should be chosen before reviewing final
test results.

If sample size or market coverage is inadequate, verdict is
**INCONCLUSIVE**, not PASS.

### Phase H --- Freeze candidate and live paper evaluation

After a candidate passes historical qualification:

1.  Assign an immutable strategy version.
2.  Save its full configuration and code commit.
3.  Record risk settings and execution assumptions.
4.  Create a frozen evaluation profile.
5.  Prevent research experiments from modifying that profile.
6.  Run live paper trading using current market data.
7.  Record every signal, decision, order, fill, cost, risk rejection,
    and operational event.
8.  Monitor health without changing strategy rules.

The current project roadmap uses at least 30 calendar days and at least
30 trades as an initial evaluation minimum. This is a starting
operational gate, not proof of statistical confidence or durable
profitability. Extend the test if there are too few trades, limited
market diversity, or unstable results.

A strategy change during the evaluation invalidates the current
evaluation run. Start a new run with a new identifier if a change is
approved.

### Phase I --- Paper evaluation review

Compare live paper results with the historical expectations: - net
return and expectancy; - profit factor; - drawdown; - trade count and
frequency; - holding time; - win/loss distribution; - fees, spread, and
slippage; - signal-to-fill differences; - performance by market
condition; - risk-control activations; - data outages and recovery; -
state reconciliation and duplicate-order checks.

Classify the result: - **PASS TO DEMO REVIEW:** all predeclared criteria
passed and no critical defect. - **FAIL:** a mandatory criterion
failed. - **INCONCLUSIVE:** insufficient observations, market coverage,
or data quality. - **OPERATIONAL FAIL:** software, data, accounting, or
execution defects invalidate the performance evidence.

### Phase J --- Exchange demo and deployment review

Exchange demo is a separate integration test, not a profitability test.
Verify authentication, order lifecycle, cancellation, partial fills,
rejects, reconnects, restart recovery, and balance reconciliation.

Real-money readiness requires a separate human-approved review. No
research result automatically enables live trading.

## 5. Parallel work without contaminating evaluation

Two isolated tracks may run simultaneously:

### Research track

-   Develop and backtest new candidates.
-   Store each experiment separately.
-   May change candidate rules.
-   Must not control the frozen paper runner.

### Frozen evaluation track

-   Runs one immutable candidate.
-   No strategy-rule changes.
-   Records live paper evidence.
-   Any code or configuration change that affects behavior requires a
    new evaluation run.

## 6. Research outputs

Each candidate must produce: 1. Hypothesis document. 2. Experiment
record. 3. Backtest report. 4. Walk-forward report. 5. Robustness
report. 6. Failure/diagnosis report if rejected. 7. Qualification
decision with evidence. 8. Frozen evaluation configuration if approved.
9. Paper evaluation report. 10. Final promotion decision.

## 7. Non-goals

This plan does not promise: - 90% returns; - daily profits; - a fixed
monthly return; - guaranteed profitability; - a specific time to recover
losses; - automatic live deployment.

The system must optimize for evidence quality, positive net expectancy,
and controlled risk---not a predetermined extraordinary return target.
