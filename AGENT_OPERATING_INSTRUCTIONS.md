# Agent Operating Instructions

## Mission

Help develop a rigorous research and evaluation framework for the
existing BTC/USDT spot-only intraday trend-momentum trading bot.

The current strategy direction remains **intraday trend-momentum**: -
Market: BTC/USDT. - Product: spot only. - Direction: long-only unless
the owner explicitly changes scope. - Decision timeframe: 15-minute
candles. - Trend confirmation: 1-hour candles. - Current baseline:
`trend_momentum` v1.0. - Current execution mode: paper trading only.

Do not switch the project to scalping, futures, margin, leverage,
shorting, or another asset unless the owner explicitly authorizes that
change.

## First action: inspect, do not assume

Before changing code:

1.  Inspect the repository structure and existing documentation.
2.  Read the current strategy, backtester, risk manager, paper broker,
    database schema, runner, dashboard, and tests.
3.  Map each requirement in this documentation pack to:
    -   already implemented and tested;
    -   partially implemented;
    -   not implemented;
    -   unknown / needs verification.
4.  Produce a concise gap report with file paths and relevant
    function/class names.
5.  Do not rebuild existing functionality merely because this pack
    mentions it.
6.  Do not claim a capability exists unless code and tests support that
    claim.

## Preserve the existing baseline

-   Preserve `trend_momentum` v1.0 and its historical results.
-   Do not overwrite old strategy definitions, experiment records, or
    reports.
-   Give every materially different strategy configuration a unique
    immutable version identifier.
-   A changed strategy is a new candidate, not a silent update to an old
    version.
-   Record failed experiments as well as successful ones.

## Research must be reproducible

Every experiment must record: - dataset identity and checksum/version
where practical; - exact date range and timezone; - symbol and candle
intervals; - strategy version and full parameter configuration; -
feature definitions and warm-up rules; - risk configuration; - fee,
spread, slippage, and fill assumptions; - backtester/software version or
Git commit; - train/validation/test boundaries; - random seed for
randomized procedures; - execution timestamp; - metrics and final
verdict.

The same inputs and code version should reproduce the same deterministic
backtest result.

## Prevent data leakage and overfitting

-   Process data chronologically.
-   Never use future candles, future indicators, or future information
    in a decision.
-   Preserve the existing no-lookahead rule: a 15-minute decision may
    only use 1-hour candles that have already closed.
-   Do not tune on the final untouched test set.
-   Do not repeatedly inspect and optimize against the same
    out-of-sample period.
-   Use walk-forward evaluation and a final holdout where data volume
    permits.
-   Treat repeated parameter searches as multiple testing; record the
    number of experiments and avoid selecting a winner solely by its
    best historical return.
-   Prefer robust regions of parameter values over a single narrow
    optimum.

## Keep research and execution separated

-   Research code may evaluate candidate strategies in isolated
    simulations.
-   The live-data paper runner must execute only an explicitly selected,
    approved, frozen strategy version.
-   Research experiments must never change the running paper strategy
    automatically.
-   No strategy may promote itself.
-   Human approval is required before changing the paper-evaluation
    candidate.
-   No live-money execution code should be added as part of this
    research work.

## Risk and security rules

-   Maintain spot-only, long-only, paper-only defaults.
-   Keep live trading disabled.
-   Never add leverage, margin, borrowing, shorting, martingale, or
    averaging-down behavior.
-   Preserve kill switch, stale-data lockout, daily loss limit, drawdown
    halt, max spread, order limits, and position-sizing safeguards.
-   Never weaken or bypass a risk control to improve backtest returns.
-   Sells that close an existing position must remain possible under the
    risk policy.
-   Never log secrets, API keys, or credentials.
-   Do not add withdrawal permissions or store wallet seed phrases.
-   Do not enable exchange demo or live execution without explicit owner
    approval.

## How to implement

For each requested milestone:

1.  Explain the objective and proposed scope.
2.  Identify files likely to change.
3.  State assumptions and risks.
4.  Implement the smallest coherent change.
5.  Add or update tests.
6.  Run the relevant test suite.
7.  Report exact test results.
8.  Update documentation and experiment records.
9.  Do not proceed to the next milestone without approval if the change
    alters strategy behavior, risk policy, or execution behavior.

## Reporting style

Be direct and evidence-based. Separate: - observed facts; - measured
results; - hypotheses; - recommendations; - unresolved questions.

Never describe a strategy as profitable, robust, production-ready, or
safe based only on a short backtest or a small number of paper trades.

If evidence is insufficient, say **INCONCLUSIVE** rather than forcing a
pass/fail conclusion.
