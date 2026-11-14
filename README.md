# Trading Bot Research & Evaluation Pack

## Purpose

This pack defines a disciplined research, diagnosis, validation, and
promotion process for the existing BTC/USDT spot-only intraday
trend-momentum paper-trading system.

It is intended to be read by an agentic coding/research assistant before
it inspects or modifies the project.

## Current project facts

These facts come from the project's `MILESTONE_HANDOFF.md` (updated
2026-11-12):

-   Scope: BTC/USDT, spot only, paper trading only.
-   No real-money execution code exists.
-   M1 foundation: finished; tests pass.
-   M2 live data collector and history sync: finished; 180 days of
    15-minute and 1-hour candles were synced with zero reported gaps;
    live feed was smoke-tested.
-   M3 features: SMA, EMA, RSI, ATR, and average volume; no-lookahead
    test passes.
-   M4 strategy: `trend_momentum` v1.0, long-only; 15-minute decisions
    with 1-hour trend confirmation.
-   M5 backtester: implemented, but its profitability gate failed.
-   M6 paper simulator: implemented; reconciliation, rollback, restart,
    and duplicate-order protections tested.
-   M7: next milestone; a 30+ day paper evaluation is not complete.
-   M8 exchange demo integration: not implemented; stub intentionally
    raises `NotImplementedError`.
-   M9 order flow, M10 regime classifier, M11 news/sentiment, and M12
    ML: not implemented and optional.

### Existing v1.0 backtest result

  Period         Strategy return   Buy-and-hold
  ------------ ----------------- --------------
  Train                  -15.20%        -19.48%
  Validation             -12.41%        +33.12%
  Test                    -8.73%        -13.13%
  All                    -15.20%         -6.89%

The handoff also reports: - Win rate: 29--41%. - Profit factor:
0.34--0.50. - Strategy loses money even before costs. - Six sensitivity
variants ended near -15%. - The 15% drawdown halt fired. - M5 gate
verdict: FAILED.

Treat v1.0 as a preserved failed baseline. Do not silently overwrite it.

## Documents in this pack

1.  `AGENT_OPERATING_INSTRUCTIONS.md` --- how the coding/research agent
    must behave.
2.  `RESEARCH_AND_EVALUATION_PLAN.md` --- end-to-end research and
    testing workflow.
3.  `FAILURE_DIAGNOSIS_PLAYBOOK.md` --- structured diagnosis of losing
    performance.
4.  `STRATEGY_LIFECYCLE_AND_PROMOTION_GATES.md` --- versioning,
    acceptance gates, and promotion rules.
5.  `EXPERIMENT_TRACKING_AND_REPORTING.md` --- reproducibility, records,
    metrics, and reports.

## Important interpretation

The 30-day / 30-trade threshold is the project's initial
paper-evaluation minimum, not statistical proof of durable
profitability. More observations may be required depending on trade
frequency, variability, and market conditions.

Historical backtesting can replay the existing 180 days quickly. It does
not replace live paper evaluation, and it does not prove future returns.

## How to use this pack

-   Place these files in the project documentation directory, or copy
    their rules into the agent's project context.
-   Ask the agent to inspect the repository and map existing
    functionality to these requirements before coding.
-   Require a gap report before implementation.
-   Implement in small, reviewable milestones.
-   Keep research experiments isolated from the frozen paper-evaluation
    strategy.
