# Milestone Handoff

Source plan: `zero_budget_trading_bot_roadmap.md`
Last updated: 2026-11-12
Scope: BTC/USDT, spot only, **paper trading only** (fake money, real prices). No real-money code exists.

Legend: **FINISHED** = built and tested. **NEXT** = work to do now. **NOT DONE** = not started.

## Status board

| # | Milestone | Status | Gate result |
|---|-----------|--------|-------------|
| M0 | Manual literacy (learn by hand) | NOT DONE | User-side task, no code |
| M1 | Foundation, config, safety defaults | FINISHED | Tests pass |
| M2 | Live data collector + history sync | FINISHED | 180 days synced, 0 gaps; live feed verified |
| M3 | Features (indicators) | FINISHED | No look-ahead test passes |
| M4 | Strategy (`trend_momentum` v1.0) | FINISHED | Every decision has a reason |
| M5 | Backtester | FINISHED (built) - **gate NOT passed** | Strategy loses money out-of-sample |
| M6 | Paper-trading simulator | FINISHED | Balances reconcile; rollback + restart tested |
| M7 | MVP paper run + acceptance | **NEXT** | Software ready; needs 30+ days of paper results |
| M8 | Exchange demo API | NOT DONE | Stub raises `NotImplementedError` on purpose |
| M9 | Order-flow features | NOT DONE | Optional |
| M10 | Regime classifier | NOT DONE | Optional |
| M11 | News / sentiment | NOT DONE | Optional |
| M12 | ML research | NOT DONE | Optional |

## Development summaries (finished milestones)

### M1 - Foundation
- Python 3.11 venv, `pyproject.toml`, editable install.
- YAML profiles in `config/`: `local_sim` (default), `live_disabled`, `exchange_demo` (blocked).
- Safety defaults: live trading off, spot only, kill switch, allowlist of one symbol.
- Simple one-line logger: ✔ ok, • note, ⚠ warning, ✘ error. (`log.py`, `config.py`, `models.py`)
- SQLite database with tables for candles, decisions, orders, fills, equity, events. Journal tables are locked by triggers: rows cannot be edited or deleted. (`db.py`)

### M2 - Live data collector
- Bybit public REST history (`data/bybit.py`) and WebSocket live feed (`data/ws_feed.py`): 15m + 1h candles and best bid/ask.
- `data/sync.py`: download history, repair gaps, quality report. Result: 17,280 15m + 4,320 1h candles, 0 gaps.
- Live smoke test: connected, received prices, shut down cleanly.

### M3 - Features
- `features.py`: SMA, EMA, RSI, ATR (a measure of how much price moves), volume average.
- A 15m bar only sees 1h candles that have already closed (no peeking at the future). Unit-tested.

### M4 - Strategy
- `strategies.py`: `trend_momentum` v1.0, long-only.
  - Buy when: 1h trend up, RSI 50-70, volume above average, volatility in range, under daily trade limit, past cooldown.
  - Sell when: stop (2x ATR below), target (3x ATR above), 48 bars held, or 1h trend turns down.
- `risk.py`: allowlist, kill switch, stale-data lockout, max spread, daily loss limit, sticky drawdown halt (manual clear), max orders/day, loss-streak cooldown, position sizing. Sells are never blocked.

### M5 - Backtester (built; gate not passed)
- `backtest.py`: fills at next candle open, stop beats target in the same candle, fees + spread + slippage, chronological train/validation/test split, buy-and-hold and do-nothing benchmarks, cost stress (x1/x2/x3), sensitivity variants.
- **Result on 180 days (honest):**

| Period | Strategy | Buy-and-hold |
|--------|----------|--------------|
| Train | -15.20% | -19.48% |
| Validation | -12.41% | +33.12% |
| Test | -8.73% | -13.13% |
| All | -15.20% | -6.89% |

  - Win rate 29-41%, profit factor 0.34-0.50. Loses money even before costs, so it is not a fee problem.
  - All six sensitivity variants end near -15%.
  - The 15% drawdown halt fired and blocked further trades.
- **Gate verdict: FAILED.** The roadmap says to revise the hypothesis and repeat, keeping failed versions on record.

### M6 - Paper simulator
- `portfolio.py`: virtual cash/BTC, lot-size rounding, min order (5 USDT), no overspend/oversell, gross and net P&L tracked separately.
- `execution.py`: `PaperBroker` fills at real bid/ask plus slippage, idempotent `client_order_id` (no duplicate orders), transactional with rollback, `reconcile()` after restart (journal wins).
- `runner.py`: live loop. Decides only on closed 15m candles, watches price for stops, polls kill-switch, saves/restores state, shuts down safely.
- Account: 500 PHP virtual, about 8.62 USDT at an assumed 58 PHP/USDT.

## M7 - MVP paper run: acceptance checklist

| Check | Status |
|-------|--------|
| Live data validated | Done |
| Warm-up and gap repair | Done |
| Closed-candle / no-lookahead signals | Done (tested) |
| Reason + timestamp per signal | Done |
| Risk check before every order | Done (tested) |
| Fees / spread / slippage | Done |
| Persistence after restart | Done (tested) |
| Duplicate-order prevention | Done (tested) |
| Stale data disables entries | Done |
| Kill switch disables entries | Done (tested) |
| Daily loss limit disables entries | Done |
| Dashboard shows net P&L and drawdown | Done (`dashboard`) |
| Out-of-sample + benchmark evaluation | Done - **result negative** |
| 30+ days of paper results, no rule changes | **NOT DONE - needs calendar time** |
| All critical tests pass | Done (58 passing) |

## Research hardening (done after the gap report)
- Backtester tests: `tests/unit/test_backtest.py` (14). Research tests: `tests/unit/test_research.py` (14). Total 58 passing.
- New metrics: expectancy, avg win/loss, biggest win/loss, losing streak, drawdown duration, turnover, MFE/MAE.
- `experiments` table (immutable) + `research.py`: every backtest is saved with settings, dataset checksum, git commit.
- Final test protected: `backtest` no longer touches it; `final-check --confirm` records one look per settings + dates.
- Paper config freeze: `run` freezes settings on first start and refuses to start if they change.
- History expanded to 730 days (70,080 x 15m candles, 0 gaps). Backtest now uses the first 75% (548 days).
- **v1.0 on 2 years of data (train/validation only):** train -14.78% (buy-and-hold +4.24%), validation -13.81% (buy-and-hold -16.76%). Profit factor 0.41 / 0.18. Still FAILED. Final test not taken yet.

## Next to implement
1. **Start the paper run now** and leave it running (see commands). Do not change rules during the 30 days.
2. In parallel, **fix the strategy hypothesis** (M5 gate). Ideas: stricter entry, no-trade filter for choppy markets, different timeframe. Record every version, including failures.
3. `verdict` in the report says "TOO EARLY" until 30 days and 30 trades.
4. Only after a profitable, out-of-sample result: consider M8+.

## Commands
Run from the project folder using `.venv\Scripts\python.exe -m trading_bot <command>`:

| Command | What it does |
|---------|--------------|
| `sync` | Download/refresh candle history |
| `backtest` | Test on past data (train + validation only; final test stays locked). Every run is saved |
| `final-check` | Show whether the final test can be taken; add `--confirm` to take it. Allowed once per settings + dates |
| `experiments` | List saved backtest receipts (settings, data fingerprint, code version, results) |
| `refreeze --reason "why"` | Accept changed settings for paper trading (treat as a new experiment) |
| `run` | Start paper trading (live prices, fake money) |
| `status` | Print account, open position, verdict |
| `kill` | Emergency stop: no new buys, closes any open position |
| `resume` | Clear the kill switch |
| `dashboard` | Open the web dashboard (read-only) |

Tests: `.venv\Scripts\python.exe -m pytest -q`
