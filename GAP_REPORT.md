# Gap Report: Docs vs. Actual Code

Date: 2026-11-14
Scope: Compare the 5 research/process docs + README against what the code really does.
Nothing was changed in the code. This is read-only.

**Plain-language glossary**
- **Paper trading**: pretend trades with fake money, real prices.
- **Backtest**: replaying the strategy on old price data to see how it would have done.
- **Overfitting**: tuning a strategy so well to old data that it fails on new data.
- **Holdout / test set**: a slice of data kept hidden so it gives an honest final score. Looking at it repeatedly ruins it.
- **Walk-forward**: test on one period, then the next, then the next (like real life).
- **Drawdown**: how far the account falls from its highest point.
- **Profit factor**: total wins divided by total losses. Below 1.0 means losing money.
- **Lookahead**: accidentally using future info when deciding. A bug that fakes good results.

---

## 1. Observed facts (checked, not guessed)

- Tests: `pytest` result is **30 passed in 1.68s**.
- Git: the repo has **no commits yet**. Every file is untracked.
- Database `data/trading_bot.db` exists.
- No `research/` folder exists.
- Strategy `trend_momentum` v1.0 backtest results:

| Period | Strategy | Just holding BTC |
|---|---|---|
| Train | -15.20% | -19.48% |
| Validation | -12.41% | +33.12% |
| Test | -8.73% | -13.13% |
| All | -15.20% | -6.89% |

- Win rate 29-41%. Profit factor 0.34-0.50. It loses money even **before** fees.
- All 6 parameter variants land near -15%. The 15% drawdown stop fired.
- Per `MILESTONE_HANDOFF.md`: milestones M1-M6 done, M7 (30+ days of paper results) next.

## 2. What is done and tested (trust these)

| Capability | Where | Test |
|---|---|---|
| Live trading blocked, spot-only, symbol allowlist | `config.py` `_validate` | `test_config_safety` |
| Risk controls: kill switch, stale data, wide spread, daily loss, 15% drawdown halt, order limit, loss-streak cooldown | `risk.py` `RiskManager.check_entry` | `test_portfolio_risk_config.py` |
| Position sizing; sells never blocked | `risk.py` `size()` | yes |
| No lookahead on the 1h trend candle | `features.py` `build_features` | `test_no_lookahead_trend_candle` |
| Fees + spread + slippage; gross vs. net profit | `portfolio.py` `fill_price`, `Portfolio` | yes |
| Paper broker: no duplicate orders, rollback on failure, restart reconcile | `execution.py` `PaperBroker` | `test_db_and_broker.py` |
| Journal cannot be edited or deleted (database triggers) | `db.py` `IMMUTABLE` | yes |
| Runner cycle, restart, kill switch | `runner.py` `Runner` | `test_runner_cycle.py` |

## 3. Implemented but NOT tested

| Capability | Where | Risk |
|---|---|---|
| Whole backtester: next-candle-open fills, stop-before-target rule, chronological split, buy-and-hold benchmark, cost stress x1/x2/x3, 6 variants | `backtest.py` `run_backtest`, `split_ranges`, `with_overrides` | **High.** Every conclusion about the strategy rests on code with zero tests. |

## 4. Partial

| Doc requirement | What exists | What is missing |
|---|---|---|
| Performance metrics | win rate, profit factor, max drawdown, exposure, fees (`backtest.py` `Result`) | expectancy, avg win/loss, largest loss, losing streak, drawdown duration, turnover, MFE/MAE (best/worst price move during a trade), Sharpe/Sortino |
| Per-trade detail | entry/exit time, price, qty, gross/net, reason, bars | decision-time indicator snapshot, regime label, separate fee vs. spread vs. slippage |
| Reproducibility | paper `runs` table stores profile, version, config | no dataset checksum, no git commit, no saved backtest runs |
| Strategy versioning | version string `trend_momentum-1.0` (`strategies.py`) | nothing prevents silent edits; no config checksum |
| Paper verdict | `report.py` `verdict()` with 30 days / 30 trades minimum | uses "PROMISING" instead of docs' wording; no expected-vs-actual comparison |

## 5. Not implemented

- Experiment records and research database tables (experiments, datasets, backtest_trades, diagnoses, promotion decisions, etc.). Backtest results live **only in console output**.
- `research/` folder, hypothesis documents, comparison reports.
- Lifecycle states (DRAFT ... REJECTED/RETIRED) and Gates A-G.
- Walk-forward testing, Monte Carlo, execution-delay test, regime breakdown (M10 not built).
- Failure-diagnosis engine and report.
- Frozen paper profile (see risk 2 below).
- Count of experiments run (needed to judge luck vs. skill).
- Data audit report beyond a gap count.
- Backtest-vs-paper assumption comparison.

## 6. Unknown (not inspected, needs checking)

- `data/sync.py`, `data/bybit.py`: duplicate, out-of-order, timezone checks.
- Whether real bid/ask history is used. The backtest assumes price +/- a fixed half-spread.
- `dashboard.py`, `models.py`, `ws_feed.py` behavior.

## 7. Risks found

1. **Test set is not protected.** `cli.py` `cmd_backtest` prints train, validation and test on every run. The docs say the holdout should be looked at once.
2. **Paper strategy can change silently.** `runner.py` builds `TrendMomentum` from the current YAML. Editing `config/base.yaml` mid-evaluation changes the live paper test with no warning.
3. **Untested backtester** (see section 3).
4. **Tiny account.** About 8.62 USDT (500 PHP). Minimum order is 5 USDT, so sizing is mostly capped, and results may not reflect a bigger account.
5. **Thin data.** 180 days is short for walk-forward and for judging different market conditions.
6. **No commit history.** Experiments cannot be tied to an exact code version.
7. **30 days / 30 trades is a weak bar.** The docs admit this themselves.

## 8. Recommendations (not started, need your approval)

In this order, smallest first:

1. Make the first git commit so there is a code baseline.
2. Add backtester tests (fills, stop-vs-target, split, repeatable results).
3. Add a simple experiment log (one table or JSON file per run: config, data range, metrics, code version).
4. Add missing metrics (expectancy, avg win/loss, longest losing streak).
5. Hide the test period behind an explicit "final check" command.
6. Freeze the paper profile (refuse to start if config changed).
7. Download more history (1-2+ years) before trying new ideas.
8. Only then test **one** new idea at a time, written down before testing.

Skip for now (too heavy for a solo project): full Gates A-G, Monte Carlo, full lifecycle state machine.

## 9. Open questions

- Do you want to keep running the current v1.0 paper test, or pause until the fixes above?
- Is it OK to make the first git commit?
- How much history can we download (data source limits)?
- Should the docs be trimmed to the lighter version above?

## 10. Housekeeping note

A git command moved a stale `.git/index.lock` file to the Recycle Bin. It was a leftover lock and is almost certainly harmless. Restore it from the Recycle Bin only if something breaks.
