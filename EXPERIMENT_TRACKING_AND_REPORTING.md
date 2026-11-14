# Experiment Tracking and Reporting

## 1. Purpose

Make every strategy experiment reproducible, comparable, and auditable.

A research result without its dataset, configuration, assumptions, and
code version is not reliable evidence.

## 2. Experiment record

Create one immutable record for every experiment.

Required fields:

  Field                   Description
  ----------------------- -------------------------------------------------
  `experiment_id`         Unique ID
  `created_at_utc`        Creation timestamp
  `owner_or_agent`        Who initiated it
  `hypothesis`            Expected reason for improvement
  `strategy_id`           Strategy family
  `strategy_version`      Immutable candidate version
  `parent_version`        Baseline from which it was derived
  `change_summary`        Exact changes
  `dataset_id`            Historical dataset reference
  `dataset_checksum`      Checksum/version where practical
  `symbol`                BTC/USDT
  `timeframes`            15m and 1h unless explicitly approved otherwise
  `date_start_utc`        Start of data range
  `date_end_utc`          End of data range
  `split_definition`      Train/validation/test dates
  `feature_config`        Feature definitions and parameters
  `risk_config`           Risk rules and limits
  `fee_assumption`        Fee model
  `spread_assumption`     Spread model
  `slippage_assumption`   Slippage model
  `fill_model`            Execution/fill assumptions
  `code_commit`           Git commit or software version
  `random_seed`           Seed for stochastic tests
  `metrics`               Results
  `verdict`               PASS / FAIL / INCONCLUSIVE / INVALID
  `report_path`           Full report location
  `notes`                 Caveats and observations

## 3. Required performance metrics

At minimum report:

### Return and expectancy

-   starting and ending equity;
-   gross P&L;
-   net P&L;
-   net return;
-   average net trade;
-   expectancy per trade;
-   average winner;
-   average loser.

### Risk

-   maximum drawdown;
-   drawdown duration;
-   largest loss;
-   losing streak;
-   exposure;
-   position size distribution;
-   risk-limit activations.

### Trade quality

-   number of trades;
-   win rate;
-   profit factor;
-   average holding time;
-   turnover;
-   MFE and MAE if available.

### Costs and execution

-   total fees;
-   spread cost;
-   slippage cost;
-   estimated versus simulated fill difference;
-   rejected/partial orders if modeled.

### Robustness

-   train, validation, and test results separately;
-   walk-forward window results;
-   cost stress results;
-   parameter sensitivity;
-   market-regime breakdown;
-   Monte Carlo outcome distribution and method, if used.

Do not omit losing periods or present only aggregate returns.

## 4. Metric definitions

Use consistent definitions across reports.

-   **Net P&L:** realized and unrealized profit/loss after modeled
    trading costs.
-   **Net return:** net P&L divided by the clearly specified starting
    equity.
-   **Win rate:** winning closed trades divided by all closed trades.
-   **Profit factor:** gross profits divided by absolute gross losses.
    If gross losses are zero, report undefined/infinite explicitly
    rather than fabricating a finite value.
-   **Expectancy per trade:** mean net P&L per closed trade, with
    currency and denominator stated.
-   **Maximum drawdown:** largest peak-to-trough decline in the equity
    curve, with method stated.
-   **Sharpe/Sortino:** state return frequency, annualization method,
    risk-free assumption if used, and limitations. Do not compare ratios
    calculated with different conventions.

## 5. Diagnosis report

Every failed or inconclusive experiment should produce: 1. Verdict. 2.
Data and implementation integrity checks. 3. Key metrics. 4. Performance
by chronological segment. 5. Performance by market regime, if reliably
defined. 6. Entry/exit/cost/risk attribution. 7. Ranked hypotheses for
failure. 8. Evidence for and against each hypothesis. 9. Proposed
controlled experiments. 10. Known limitations.

## 6. Comparison report

When comparing candidates: - use the same dataset and date boundaries; -
use the same execution and cost assumptions; - use the same initial
capital and risk constraints unless the experiment explicitly studies
those differences; - report all candidates, not only the winner; -
include baseline v1.0; - include benchmark results; - show trade count
and drawdown alongside return; - explain if comparisons are not
apples-to-apples.

Do not rank candidates solely by total return.

## 7. Research database entities

The implementation may use SQLite or another project-approved store.
Inspect the existing schema before designing new tables.

Conceptual entities:

-   `datasets`
-   `strategy_versions`
-   `experiments`
-   `experiment_parameters`
-   `backtest_runs`
-   `backtest_trades`
-   `walk_forward_runs`
-   `stress_test_runs`
-   `diagnoses`
-   `strategy_candidates`
-   `paper_evaluations`
-   `promotion_decisions`
-   `artifacts`

Use immutable records for completed experiments. Corrections should
create a superseding record or explicit audit event rather than silently
rewriting historical results.

## 8. Reports and artifacts

Recommended artifact layout:

``` text
research/
  README.md
  datasets/
    dataset_manifest.json
  hypotheses/
    HYP-0001.md
  experiments/
    EXP-0001/
      experiment.json
      backtest_report.md
      trades.csv
      equity_curve.csv
      diagnosis.md
  strategies/
    trend_momentum/
      v1.0.0/
        strategy_spec.md
        config.yaml
        qualification_report.md
      v1.1.0/
        strategy_spec.md
        config.yaml
        qualification_report.md
  paper_evaluations/
    PAPER-0001/
      frozen_config.yaml
      daily_report.md
      final_report.md
  decisions/
    promotion_log.md
```

This is a recommended logical layout. Adapt it to the existing
repository rather than duplicating or disrupting its current structure.

## 9. Report language

Use precise labels: - **PASS** --- all predeclared criteria passed. -
**FAIL** --- one or more mandatory criteria failed. - **INCONCLUSIVE**
--- evidence is insufficient. - **INVALID** --- data or implementation
defects invalidate the result.

Never use "guaranteed," "sure profit," "proven to make money," or "90%
profitable" based on historical or short-duration paper results.
