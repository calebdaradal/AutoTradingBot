# Zero-Budget Algorithmic Trading Bot

## Beginner-to-paper-trading roadmap, MVP definition, setup guide, and AI-coder reference pack

**Prepared:** 12 November 2026\
**Starting cash:** ₱500 (not to be deposited until the system passes the
paper-trading gates)\
**Primary objective:** Build a beginner-friendly, autonomous
**spot-crypto** trading system that uses live market data and simulated
money.\
**Important:** This is a software-development and education plan, not a
promise of profit or personalized investment advice. A bot cannot
guarantee accurate predictions or large overnight returns. With ₱500,
protecting capital and proving the system works matter much more than
chasing large returns.

------------------------------------------------------------------------

# 0. Read this first: what you are building

You are not building a wallet, an exchange, or a new cryptocurrency. You
are building software that:

1.  Reads market information from an exchange.
2.  Calculates indicators and market conditions.
3.  Applies a written trading strategy.
4.  Decides whether a trade is allowed under strict risk rules.
5.  Sends a simulated order to a paper-trading account (or simulates the
    fill itself).
6.  Records every input, decision, order, fee, and result.
7.  Monitors itself and stops safely when something goes wrong.

**A crypto exchange account is not the same thing as a self-custody
wallet.** For exchange-based spot trading, you generally create an
account with an exchange. You do not need to create a MetaMask or other
blockchain wallet for this first project. Do not send funds to a wallet
address while setting up paper trading.

**Recommended first market:** BTC/USDT spot, one pair only. BTC is not
guaranteed to be profitable or safe; it is simply a liquid, widely
followed market that is useful for learning. No leverage, futures,
margin, borrowing, short selling, or copy trading.

**Recommended initial test architecture:** use an exchange demo/test
environment to test API order placement, and a separate internal
simulator to test realistic fills, fees, spread, slippage, partial
fills, and outages. These are different tests and both are useful.

------------------------------------------------------------------------

# 1. What counts as the MVP?

## MVP definition

The MVP is complete when the bot can run unattended against live public
market data, make decisions using a documented strategy, execute only
simulated spot trades, preserve its state after a restart, and produce a
trustworthy performance report.

The MVP does **not** need AI, news sentiment, machine learning, multiple
coins, multiple strategies, a cloud server, or real-money execution.

### MVP scope

  ------------------------------------------------------------------------
  Capability                       Required for MVP? Notes
  --------------------- ---------------------------- ---------------------
  Live BTC/USDT market                           Yes Public API; no
  data                                               trading key needed

  Historical candle                              Yes For warm-up and
  download                                           backtesting

  Indicator                                      Yes Deterministic and
  calculations                                       testable

  One written strategy                           Yes Start simple; avoid
                                                     strategy shopping

  Risk checks                                    Yes Must run before every
                                                     simulated order

  Paper execution                                Yes Internal simulator
                                                     first; exchange demo
                                                     second

  Fees and slippage                              Yes Never report gross
                                                     profit as net profit

  Trade journal and                              Yes Persist all decisions
  database                                           and fills

  Restart/recovery                               Yes No duplicate trades
                                                     after restart

  Monitoring and kill                            Yes Stop opening trades
  switch                                             if data/system is
                                                     unsafe

  Dashboard/report                               Yes Balance, equity,
                                                     drawdown, fees, trade
                                                     log

  AI/LLM                                          No Keep execution
  decision-making                                    decisions
                                                     deterministic

  Machine learning                                No Add only after a
                                                     baseline is proven

  News/sentiment                                  No Optional later

  Live deposits and                               No Outside the MVP
  trading                                            
  ------------------------------------------------------------------------

**MVP milestone boundary:** The system becomes a viable *paper-trading
MVP* at Milestone 7 below, once all acceptance tests pass. It is not yet
a viable real-money trading system.

------------------------------------------------------------------------

# 2. Zero-cost-first technology choices

Costs and free-tier limits can change. Verify current official terms
before relying on any provider. "Free API" means no subscription for the
documented public endpoints; it does not mean unlimited access,
guaranteed uptime, or free trading.

  -------------------------------------------------------------------------
  Need              First choice      Why                 Cost approach
  ----------------- ----------------- ------------------- -----------------
  Language          Python            Large ecosystem and Free
                                      approachable for    
                                      data work           

  Exchange market   Bybit public V5   Public market       Public endpoints,
  data              REST/WebSocket,   feeds; BTC spot     rate-limited
                    if accessible     candles, ticker,    
                                      trades, order book  

  Demo exchange     Bybit Demo        Simulated           No real funds;
  execution         Trading API, if   account/order       demo API
                    accessible        endpoints           limitations apply

  Alternative spot  Binance Spot Test Simulated assets    Free test
  test environment  Network           and test API        environment;
                                                          separate from
                                                          live

  Exchange          Native exchange   Native SDK avoids   Open source
  abstraction       SDK first; CCXT   hiding              
                    later if useful   exchange-specific   
                                      behavior; CCXT      
                                      helps portability   

  Indicators/data   pandas, NumPy;    Local calculations  Free/open source
                    optionally                            
                    pandas-ta or                          
                    TA-Lib                                

  Backtesting       Backtesting.py or Historical strategy Check current
                    vectorbt          testing             package terms
                    Community, or a                       
                    small custom                          
                    simulator                             

  Storage           SQLite            Single-computer MVP Free
                                      database            

  Dashboard         Streamlit         Local dashboard     Free locally

  Testing           pytest            Unit/integration    Free
                                      tests               

  Logging           Python logging /  Audit trail and     Free
                    structlog         troubleshooting     

  Version control   Git               Track code and      Free locally
                                      strategy changes    

  Scheduling        Windows Task      Run at startup /    Included with
                    Scheduler         restart             Windows
                    initially                             

  AI coding         Your existing     Avoid paid AI       Depends on your
  assistant         model/editor,     dependencies in the existing setup
                    with local        bot itself          
                    documentation                         
                    pack                                  
  -------------------------------------------------------------------------

## Provider notes and important corrections

### Bybit Demo Trading

Official documentation: https://bybit-exchange.github.io/docs/v5/demo

The current documentation says demo trading is an isolated environment.
Demo API keys are created after signing in to a main account and
switching to Demo Trading. The demo REST host is
`https://api-demo.bybit.com`; demo private WebSocket is
`wss://stream-demo.bybit.com`. Public market data is the same as mainnet
public data, using the normal public feed. The documentation warns that
not every API is available in demo, and demo orders are retained for
seven days.

**Do not mix environments:** use demo keys only with demo endpoints.
Never place live keys in a demo configuration or vice versa. Demo keys
are not interchangeable with production keys.

The official documentation also describes a demo-funds endpoint. Use the
website's demo UI first if possible; use the API for fund allocation
only after the coder has implemented and tested it safely.

### Binance Spot Test Network

Official documentation:
https://developers.binance.com/docs/binance-spot-api-docs/testnet

The Spot Test Network provides virtual balances and a separate API
environment. The current documentation identifies test REST and
WebSocket endpoints and notes that only specified `/api` endpoints are
supported (not `/sapi`). Testnet funds cannot be transferred to or from
the live exchange.

**Important:** Testnet is for software testing, not proof that live
liquidity, fills, spreads, or execution quality will match production.

### CCXT

Official manual: https://docs.ccxt.com/

CCXT supports many exchange APIs and documents sandbox/testnet support
where the exchange supports it. Its sandbox mode must be enabled
immediately after constructing the exchange object, before other calls.
Sandbox keys and production keys are not interchangeable. CCXT does not
magically make every exchange feature identical or supported.

For the first MVP, prefer one exchange's official API/SDK for the demo
adapter. Add CCXT only if there is a clear need.

### Free market-data fallback

If demo trading is inaccessible from your region/account, the MVP can
still paper trade using public live market data and an internal
simulator. The bot does not need an exchange account or API key to read
public market data from an exchange's public endpoints, subject to that
exchange's terms and rate limits.

Do not add CoinGecko, CoinMarketCap, or several aggregators on day one.
One consistent exchange feed is easier to validate. Aggregated provider
prices may differ from the exact venue where simulated orders are
supposedly filled.

------------------------------------------------------------------------

# 3. Beginner platform setup: do this before coding order execution

You said you have no trading-platform knowledge. Follow this sequence
and do not deposit money.

## Step 1 --- Learn the basic terms

-   **Exchange:** A platform where users buy and sell crypto.
-   **Trading pair:** Two assets quoted against each other. `BTC/USDT`
    means the BTC price is expressed in USDT.
-   **Spot:** Buying/selling the actual asset in an exchange account.
    This project uses spot only.
-   **Stablecoin:** A token designed to track a reference currency. USDT
    aims to track the US dollar but still has issuer, market, platform,
    and regulatory risks.
-   **Order:** An instruction to buy or sell.
-   **Market order:** Requests immediate execution at available prices;
    final price can vary.
-   **Limit order:** Sets a maximum buy price or minimum sell price; it
    may not fill.
-   **Bid/ask:** Best displayed buy/sell prices.
-   **Spread:** Difference between best ask and best bid.
-   **Liquidity:** How much can be traded without moving the price
    significantly.
-   **Fee:** Exchange charge for a trade. Maker/taker fees may differ.
-   **Slippage:** Difference between expected and actual fill price.
-   **Candle/OHLCV:** Open, high, low, close, and volume over a time
    interval.
-   **API key:** Credential that lets software access an account or API.
    Treat it like a password.
-   **Paper trading:** Simulated trading with virtual funds.
-   **Backtesting:** Running a strategy over historical data.
-   **Drawdown:** Decline from an account's previous equity peak.

Do not confuse a profitable backtest with a reliable live strategy.

## Step 2 --- Choose one exchange environment

Start with **Bybit Demo Trading only if you can legitimately access and
use it from the Philippines and satisfy its current account
requirements**. If not, use Binance Spot Test Network only if its
current access and requirements are suitable. Otherwise use the internal
simulator.

Before registering or providing identity documents: 1. Visit the
provider's official website yourself (not a link sent by a stranger). 2.
Read its current supported-country and restricted-country terms. 3.
Check the relevant Philippine regulatory information and current local
availability. 4. Confirm you understand the provider's custody,
withdrawal, fee, and dispute policies. 5. Do not use a VPN to bypass
geographic restrictions or identity checks. 6. Do not assume that a
globally accessible website is legally or operationally available to
Philippine residents.

Philippine regulatory starting points: - SEC advisories:
https://www.sec.gov.ph/investor-education-and-information/advisories/ -
BSP: https://www.bsp.gov.ph/

Regulatory requirements and platform status can change. Verify current
official notices immediately before opening or funding an account. This
guide does not determine whether a particular exchange is authorized to
serve you.

## Step 3 --- Create a demo/test account

### If using Bybit Demo

1.  Navigate to Bybit's official website and sign in/create an account
    only if its current terms allow you to do so.
2.  Complete only the verification required by the platform. Do not
    submit documents through unofficial links or chat messages.
3.  Find the account menu and switch to **Demo Trading**.
4.  Confirm that the interface clearly indicates Demo Trading.
5.  Locate the demo assets/balance page and note the virtual balances.
6.  Open the API management area while still in the demo environment.
7.  Create a dedicated demo API key.
8.  Give the key only the permissions needed for the MVP: read
    market/account information and place/manage demo orders.
9.  Do not enable withdrawals, transfers, or unrelated permissions.
10. Save the key and secret in a local environment file that is excluded
    from Git.
11. Confirm the key works against the demo REST endpoint, not the
    production endpoint.

Bybit's demo API documentation:
https://bybit-exchange.github.io/docs/v5/demo

### If using Binance Spot Test Network

1.  Open the official Spot Test Network website from Binance's developer
    documentation.
2.  Sign in using the test-network process described in the current
    documentation.
3.  Create a test API key there.
4.  Confirm the account displays virtual assets.
5.  Use only the test-network endpoints shown in the official docs.
6.  Do not use a production API key on testnet or a testnet key on
    production.

Official documentation:
https://developers.binance.com/docs/binance-spot-api-docs/testnet

### If neither exchange demo is available

Do not let account access block development. Use the internal
simulator: 1. Connect to a public exchange market-data feed. 2. Set an
artificial account balance (for example, ₱500 converted to a chosen
quote currency using a recorded FX rate, or simply a round virtual USDT
balance). 3. Simulate orders using bid/ask prices and trade/order-book
updates. 4. Deduct assumed fees and slippage. 5. Save all simulated
fills and account changes in SQLite.

An internal simulator is often better for repeatable testing because you
control its assumptions and can test edge cases.

## Step 4 --- Understand API-key safety

-   Never paste secrets into source code, prompts, screenshots, GitHub,
    logs, or chat.
-   Use environment variables or a local `.env` file; add `.env` to
    `.gitignore`.
-   Keep separate credentials/configurations for demo and live.
-   For paper trading, disable withdrawal and transfer permissions
    entirely.
-   If supported, restrict API access by IP.
-   Use a dedicated API key only for this bot.
-   Rotate/revoke the key immediately if it may have leaked.
-   Never let an LLM see or print secrets.
-   Never store seed phrases or private wallet keys in the bot. This
    project does not need a self-custody wallet.

------------------------------------------------------------------------

# 4. Milestone plan

The milestone order is deliberately conservative. Each milestone
includes a goal, procedures, deliverables, and a gate. Do not move
forward just because code runs once.

## Milestone 0 --- Trading and platform literacy

**Goal:** Understand the mechanics well enough to know what the bot is
doing.

### Procedures

1.  Read the glossary in Section 3.
2.  Open the exchange's demo interface (or test network).
3.  Find BTC/USDT Spot.
4.  Identify the last price, bid, ask, spread, 24-hour volume, and chart
    interval.
5.  Switch chart intervals between 1m, 5m, 15m, 1h, and 4h.
6.  Find the order panel and learn the difference between market and
    limit orders.
7.  Place one tiny virtual limit order in demo, observe whether it
    fills, then cancel it.
8.  Find order history, trade history, balances, and fees.
9.  Record screenshots or notes for your own reference. Never include
    API secrets.

### Deliverables

-   One-page personal glossary.
-   Screenshots/notes identifying the key interface areas.
-   A successful demo order and cancellation.

### Gate

You can explain what pair, order type, bid/ask, spread, fee, fill, and
paper trading mean. No real deposit.

------------------------------------------------------------------------

## Milestone 1 --- Project foundation and safe configuration

**Goal:** Create a reliable local Python project before touching trading
logic.

### Procedures

1.  Install a supported Python version (prefer a currently supported
    stable release).
2.  Install Git.
3.  Create a project folder and virtual environment.
4.  Add dependency pinning (`requirements.txt` or `pyproject.toml` with
    locked versions).
5.  Create `.env.example` containing placeholder names only.
6.  Add `.env`, database files, logs, and secrets to `.gitignore`.
7.  Set up structured logging with timestamps and log levels.
8.  Set up `pytest`.
9.  Add separate configuration profiles: `local_sim`, `exchange_demo`,
    and `live_disabled`.
10. Make `live_disabled` the default. The first version should not
    contain a functioning live-order path.

### Deliverables

-   Reproducible project setup.
-   README with setup/run/test instructions.
-   No secrets in Git history.
-   Tests run successfully.

### Gate

A clean checkout can be installed and tested from the README. The
application starts in simulator mode by default.

------------------------------------------------------------------------

## Milestone 2 --- Live public market-data collector

**Goal:** Receive and store live BTC/USDT data without placing any
orders.

### Procedures

1.  Choose one exchange feed (Bybit public Spot feed if accessible).
2.  Read its official documentation for ticker, kline/candlestick,
    recent trades, and order-book topics.
3.  Start with REST historical candles to warm up the indicator
    calculations.
4.  Connect to the public WebSocket feed for live updates.
5.  Subscribe only to BTCUSDT Spot at first.
6.  Store timestamps in UTC internally; display local time separately.
7.  Validate candle intervals and ensure only closed candles are used
    for close-of-candle signals.
8.  Detect missing, duplicate, out-of-order, stale, and malformed
    messages.
9.  Reconnect with bounded exponential backoff and jitter.
10. On reconnect, fetch missing historical candles to repair data gaps.
11. Log data age, connection status, and last successful update.
12. Do not assume WebSocket messages arrive exactly once or in perfect
    order.

### Deliverables

-   Live BTC/USDT price display.
-   Historical candle database.
-   Data-quality report.
-   Reconnect and gap-recovery tests.

### Gate

Run for at least 24 hours with no unexplained data gaps. If a gap
occurs, it is detected, logged, and repaired. The bot must refuse to
create a signal from stale or incomplete data.

------------------------------------------------------------------------

## Milestone 3 --- Indicator and market-feature engine

**Goal:** Convert raw data into reproducible features.

### Start with a small set

-   EMA 20 and EMA 50: trend context.
-   RSI 14: momentum context.
-   ATR 14: volatility and stop-distance input.
-   Volume moving average: unusual volume context.
-   Optional MACD only after the first set is verified.

Do not add every indicator you find online. Many indicators are
transformations of the same price data and can create false confidence.

### Procedures

1.  Implement each indicator using a well-understood library or
    independently verified formula.
2.  Document the candle timeframe and parameter for each feature.
3.  Handle warm-up periods; early rows with insufficient history must be
    marked unavailable, not filled with invented values.
4.  Test indicator outputs against a trusted independent calculation on
    fixed sample data.
5.  Check for look-ahead bias: a signal at candle close cannot use the
    next candle's high/low/close.
6.  Store the feature values and the source candle timestamp.
7.  Add tests for missing data, zero volume, flat prices, and extreme
    values.

### Deliverables

-   Feature table and indicator tests.
-   A chart/report showing candles and indicators.
-   Feature documentation.

### Gate

The same historical input produces the same output every time. No
indicator uses future data.

------------------------------------------------------------------------

## Milestone 4 --- One simple, explicit strategy

**Goal:** Create one understandable baseline strategy, not an AI
guessing system.

### Strategy design principles

1.  Write the rules in plain language before coding.
2.  Use closed candles for signal generation.
3.  Use a higher timeframe only as a filter if it is fully closed and
    timestamp-aligned.
4.  Define exact entry, exit, invalidation, and no-trade conditions.
5.  Define what happens when indicators disagree.
6.  Define a maximum number of trades per day.
7.  Include a cooldown after a trade if the strategy requires it.
8.  Record the reason for every signal, including rejected signals.

### Example baseline (for testing, not a recommendation to trade)

-   Use 1-hour candles to define broad trend context.
-   Consider a long setup only when EMA 20 is above EMA 50 on a fully
    closed 1-hour candle.
-   Use a 15-minute candle close for entry evaluation.
-   Require a defined momentum/volume condition.
-   Place a hypothetical entry only if estimated fees and spread do not
    make the expected trade uneconomic.
-   Exit based on a pre-defined invalidation/stop or strategy exit rule.
-   Do not enter if data is stale, spread is too wide, volatility is
    outside tested bounds, or risk checks fail.

The coder must not silently optimize the thresholds on the same data
used to report performance.

### Deliverables

-   Strategy specification.
-   Signal generator.
-   Signal/rejection journal.
-   Unit tests for every rule.

### Gate

Given the same candle history, the strategy produces identical signals
and a human can explain why each one occurred.

------------------------------------------------------------------------

## Milestone 5 --- Backtesting with realistic costs

**Goal:** Test the baseline against historical data before paper
execution.

### Procedures

1.  Obtain historical BTC/USDT spot candles from the chosen venue.
2.  Check for missing intervals, duplicates, timezone errors, and bad
    values.
3.  Separate data into:
    -   development/training period,
    -   validation period,
    -   untouched out-of-sample test period.
4.  Keep chronological order; never randomly shuffle time-series data.
5.  Simulate order timing realistically. A signal generated after a
    candle closes cannot fill at a price that was only known before that
    close.
6.  Model maker/taker fees using the current fee schedule applicable to
    the account tier; do not hard-code an assumed fee forever.
7.  Include spread and slippage assumptions.
8.  Include limit orders that may not fill, and market orders that can
    slip.
9.  Track partial fills where relevant.
10. Compare performance with a simple buy-and-hold benchmark and a
    no-trade baseline.
11. Run sensitivity tests with worse fees/slippage.
12. Test different market regimes, not just one favorable period.

### Metrics to report

-   Net return after estimated costs.
-   Maximum drawdown.
-   Profit factor.
-   Average net trade.
-   Win rate (not sufficient by itself).
-   Number of trades.
-   Exposure/time in market.
-   Largest loss and losing streak.
-   Sharpe/Sortino only with clearly documented assumptions.
-   Performance by month/regime.
-   Comparison with benchmark.

### Deliverables

-   Reproducible backtest report.
-   Data-quality report.
-   Cost assumptions.
-   Out-of-sample results.

### Gate

The strategy is not accepted merely because total return is positive. It
must survive out-of-sample testing, cost stress tests, and a comparison
to a simple benchmark. If it fails, revise the hypothesis and repeat
without hiding failed versions.

------------------------------------------------------------------------

## Milestone 6 --- Internal paper-trading simulator

**Goal:** Simulate live trading using live market data without placing
any exchange order.

This is the most important milestone for a zero-budget project.

### Procedures

1.  Create a virtual account with a configurable starting balance.
2.  Store the quote currency and FX conversion assumption if presenting
    results in PHP.
3.  Implement spot-only buy/sell accounting.
4.  Simulate market buys at the ask plus slippage.
5.  Simulate market sells at the bid minus slippage.
6.  For limit orders, do not fill simply because the candle touched the
    limit price. Use conservative assumptions and document limitations;
    ideally use trade/order-book data to model queue uncertainty.
7.  Deduct trading fees on each fill.
8.  Track available cash, asset quantity, average entry cost, realized
    P&L, unrealized P&L, and equity.
9.  Reject orders below exchange minimum notional/quantity/precision
    rules when modelling a specific exchange.
10. Prevent selling more BTC than the virtual account owns.
11. Prevent duplicate orders after restarts.
12. Persist state transactionally in SQLite.
13. Test partial fills, rejected orders, API/data outages, clock drift,
    process crashes, and restart recovery.
14. Keep a complete immutable decision/order/fill journal.
15. Display gross and net P&L separately.

### Deliverables

-   Internal simulator.
-   Virtual balance/equity ledger.
-   Paper order and fill journal.
-   Fee/spread/slippage configuration.
-   Recovery and failure tests.

### Gate

The simulator's balances reconcile exactly after every trade. It never
creates money or negative asset balances accidentally. All fees and
simulated fill assumptions are visible.

------------------------------------------------------------------------

## Milestone 7 --- First viable paper-trading MVP

**Goal:** Run the complete strategy unattended on live data with virtual
money.

### Procedures

1.  Connect Milestones 2--6.
2.  Start with one pair, one strategy, spot only.
3.  Start with conservative virtual capital that resembles your eventual
    small account, but do not assume an exchange will accept such a
    small real order.
4.  Keep all live-order functions disabled.
5.  Run continuously for at least 30 days as a first observation period;
    60--90 days is more informative if the strategy trades infrequently.
6.  Review the bot daily at first, even if it is designed to run
    overnight.
7.  Compare every signal to the stored market data and strategy
    explanation.
8.  Record software crashes, data gaps, rejected signals, simulated
    fills, and recovery events.
9.  Do not change strategy parameters mid-test without creating a new
    version and restarting the evaluation window.
10. At the end, report net performance after costs, drawdown, number of
    trades, benchmark comparison, and operational uptime.

### MVP acceptance checklist

-   [ ] Live public market data is received and validated.
-   [ ] Historical warm-up and reconnect gap repair work.
-   [ ] Signals use closed candles and no future information.
-   [ ] Every signal has a reason and timestamp.
-   [ ] Risk rules are applied before every simulated order.
-   [ ] Fees, spread, and slippage are included.
-   [ ] Orders/fills/balances persist after restart.
-   [ ] Duplicate orders are prevented.
-   [ ] Stale data disables new entries.
-   [ ] Emergency stop disables new entries.
-   [ ] Daily loss limit disables new entries.
-   [ ] Dashboard reports net P&L and drawdown accurately.
-   [ ] Strategy is evaluated out of sample and against a benchmark.
-   [ ] 30+ days of paper results are recorded without changing the
    rules mid-run.
-   [ ] All critical tests pass.

**This is the paper-trading MVP milestone.** Passing it means the
software is ready for more rigorous evaluation, not that the strategy is
profitable or safe for real funds.

------------------------------------------------------------------------

# 5. Optional upgrades after the MVP

Add these one at a time. Measure whether each improves out-of-sample
results after costs. More data and more AI do not automatically mean
better trades.

## Milestone 8 --- Exchange demo API integration

Use Bybit Demo or Binance Spot Test Network to test authenticated API
behavior: - API authentication and signatures. - Place/cancel order. -
Query open orders and order history. - Query executions/fills. - Query
virtual balance. - Handle rate limits and errors. - Reconcile local
state against exchange state.

Keep the internal simulator as the repeatable research environment.
Exchange demos may have different liquidity/fill behavior and may retain
only limited history.

## Milestone 9 --- Order-flow and microstructure features

Possible inputs: - Bid/ask spread. - Order-book depth at multiple
levels. - Order-book imbalance. - Recent trade aggressor direction, if
provided. - Volume bursts. - Liquidity changes.

Warnings: - Displayed orders can be cancelled. - Order books can be
spoofed or misleading. - A snapshot is not a guarantee of fillability. -
High-frequency order-book data can be noisy and operationally
expensive. - Do not infer hidden institutional intent from a single
large order.

## Milestone 10 --- Market-regime classifier

Classify conditions such as: - trending, - ranging, - high volatility, -
low volatility, - abnormal/dislocated market.

Begin with transparent rules and test them. A classifier should be
allowed to say "uncertain / do not trade."

## Milestone 11 --- News and sentiment

Only add if you have a stable, legal, free data source with clear usage
limits. Record source, publication time, retrieval time, and any
missing-data state. News can be delayed, duplicated, manipulated, or
irrelevant. Never let an LLM turn a headline directly into an order.

## Milestone 12 --- Machine learning research

Only after the deterministic baseline has a reliable paper-trading
record: - Define a prediction target carefully. - Use chronological
train/validation/test splits. - Prevent data leakage. - Compare against
simple baselines. - Include fees and execution constraints. - Monitor
model drift. - Require human approval before model/strategy changes
reach paper or live environments.

Avoid training a model to predict the next candle and assuming that
prediction translates into profitable execution.

------------------------------------------------------------------------

# 6. What "accuracy" really means in trading

There is no setting that makes a trading bot highly accurate in all
market conditions. A high win rate can still lose money if losses are
much larger than wins. A lower win rate can be profitable if average
wins sufficiently exceed average losses, after costs.

Focus on these principles:

1.  **Data correctness before indicators.** Bad timestamps, missing
    candles, duplicate messages, and wrong symbol mapping corrupt every
    later layer.
2.  **No look-ahead bias.** Never use future candle values to make a
    past decision.
3.  **No survivorship bias.** If you later test multiple coins, include
    delisted/failed assets where relevant.
4.  **Chronological testing.** Keep a genuinely untouched out-of-sample
    period.
5.  **Account for costs.** Fees, spread, slippage, funding (not
    applicable to spot), and minimum order sizes matter.
6.  **Avoid overfitting.** Too many indicators, parameters, and filters
    can make historical results look impressive but fail live.
7.  **Use one hypothesis at a time.** Change one meaningful thing,
    version it, and retest.
8.  **Benchmark honestly.** Compare with buy-and-hold and no-trade.
9.  **Allow no-trade decisions.** The bot should not be forced to trade
    every day.
10. **Keep risk separate from prediction.** A strong signal does not
    override a risk limit.
11. **Monitor operational risk.** Network outages, API changes, exchange
    maintenance, clock drift, and software bugs can lose money even if
    the strategy is sound.
12. **Do not let AI improvise execution.** LLM output is
    non-deterministic and can hallucinate. It may summarize or explain;
    deterministic, tested code must enforce trading rules.

------------------------------------------------------------------------

# 7. Risk controls to implement before any live mode

For a tiny account, minimum order sizes and fees may make sensible risk
sizing impossible. If the smallest valid order risks more than the
allowed amount, the correct action is **do not trade**.

Mandatory controls: - Spot-only allowlist. - One symbol allowlist
initially (`BTCUSDT`). - Leverage/margin/futures disabled. - Maximum
position exposure. - Maximum daily loss and drawdown stop. - Maximum
number of new orders per day. - Cooldown after consecutive losses. - No
martingale or loss-recovery sizing. - No automatic averaging down. -
Spread and volatility filters. - Stale-data lockout. - API error
lockout. - Duplicate-order idempotency. - Startup reconciliation of
local state and exchange state. - Emergency stop that blocks new
entries. - A separate manual process for any future live-mode
enablement.

**Never rely on a stop-loss alone.** A stop can slip, fail, or execute
differently than expected during gaps or outages. Risk sizing and
position limits are still required.

------------------------------------------------------------------------

# 8. Preparing for ₱500 live trading --- only after paper validation

This section is a future checklist, not an instruction to deposit now.

Before considering a live deposit: 1. Recheck Philippine regulatory
status and whether the chosen provider is permitted to serve your
account. 2. Confirm the provider supports PHP deposits/withdrawals for
your account and understand all fees and limits. 3. Check the exchange's
minimum spot order size, quantity step, tick size, and fee schedule for
BTC/USDT. 4. Calculate the smallest possible order's total fee and
potential loss. 5. Verify that ₱500 is money you can afford to lose
entirely without affecting food, bills, debt, transport, or emergencies.
6. If the minimum order or fee structure makes the risk rules
impossible, do not deposit just to force a trade. 7. Do not borrow money
or use leverage. 8. Use a separate API key with trading permission only;
disable withdrawal and transfer permission. 9. If supported, restrict
API access by IP. 10. Keep a manual emergency process to cancel open
orders and disable the bot. 11. Start with the smallest allowed order
only if it fits the written risk budget. 12. Keep the bot in paper mode
until a deliberate, separately reviewed live-mode change is made.

## Future live activation checklist

-   [ ] Platform availability and regulatory status checked from
    official sources.
-   [ ] Deposit and withdrawal methods/fees understood.
-   [ ] Minimum notional, precision, and trading fees verified.
-   [ ] Money is genuinely disposable.
-   [ ] Strategy has passed the paper gates.
-   [ ] API key has no withdrawal/transfer permission.
-   [ ] Live keys are stored separately from demo keys.
-   [ ] Live mode requires an explicit manual confirmation.
-   [ ] Initial order size is within risk limits.
-   [ ] Emergency shutdown has been tested.
-   [ ] First live order is monitored manually.

Do not automate deposits or withdrawals. Do not let the bot move funds
between accounts.

------------------------------------------------------------------------

# 9. Suggested project structure

``` text
trading-bot/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── config/
│   ├── base.yaml
│   ├── simulator.yaml
│   ├── exchange_demo.yaml
│   └── live_disabled.yaml
├── docs/
│   ├── trading_glossary.md
│   ├── strategy_spec.md
│   ├── risk_policy.md
│   ├── data_dictionary.md
│   └── operations_runbook.md
├── src/
│   └── trading_bot/
│       ├── data/
│       ├── features/
│       ├── strategies/
│       ├── risk/
│       ├── execution/
│       │   ├── interfaces.py
│       │   ├── simulator.py
│       │   └── exchange_demo.py
│       ├── portfolio/
│       ├── monitoring/
│       ├── reporting/
│       └── app.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── failure_cases/
├── scripts/
├── data/                 # ignored by Git
├── logs/                 # ignored by Git
└── .env                  # ignored by Git; never commit
```

The live executor should not be implemented in the MVP. If it is added
later, it must be a separate adapter with explicit manual activation and
additional tests.

------------------------------------------------------------------------

# 10. AI-coder skills and reference material to provide

You asked what skills to give your AI coding model so it develops the
system with better domain knowledge. Do not give it a vague instruction
like "be an expert trader." Give it a set of bounded engineering roles,
official reference documents, and project rules.

## Recommended skill pack

  ------------------------------------------------------------------------------------------------
  Skill / role            What the coder must     Suggested reference
                          know                    
  ----------------------- ----------------------- ------------------------------------------------
  Python backend          Async programming,      Python tutorial:
  engineering             typing, packaging,      https://docs.python.org/3/tutorial/
                          error handling, clean   
                          architecture            

  Exchange API            REST, WebSockets,       Bybit V5 docs:
  integration             authentication,         https://bybit-exchange.github.io/docs/v5/intro
                          signatures, rate        
                          limits, reconnects,     
                          idempotency             

  Quantitative finance    Returns, volatility,    QuantStart: https://www.quantstart.com/
  fundamentals            risk/reward, drawdown,  
                          expectancy, benchmark   
                          comparison              

  Time-series data        Candle construction,    pandas: https://pandas.pydata.org/docs/
  engineering             timestamps, missing     
                          data, resampling,       
                          leakage prevention      

  Backtesting and         Event-driven            Backtesting.py:
  research                simulation,             https://kernc.github.io/backtesting.py/
                          out-of-sample tests,    
                          transaction costs,      
                          realistic fills         

  Market microstructure   Bid/ask, spread,        Exchange market-data/order docs
                          liquidity, order types, 
                          partial fills,          
                          order-book limits       

  Risk management         Position sizing,        Write a project-specific risk policy
                          exposure, drawdown      
                          limits, kill switches,  
                          failure modes           

  Testing and QA          Unit, integration,      pytest: https://docs.pytest.org/
                          property-based, replay, 
                          fault-injection tests   

  Security engineering    Secrets, least          OWASP: https://owasp.org/
                          privilege, API-key      
                          handling, dependency    
                          hygiene                 

  Observability/SRE       Structured logs, health OpenTelemetry: https://opentelemetry.io/docs/
                          checks, metrics,        
                          alerts, recovery, state 
                          reconciliation          
  ------------------------------------------------------------------------------------------------

These are knowledge areas, not necessarily paid or installable "AI
skills." They can be implemented as separate instruction files in the
coding workspace.

## Suggested AI-coder instruction files

Create these files in the repository and ask the coding model to read
them before each task:

1.  `AGENTS.md` --- global rules, architecture, coding standards, and
    safety constraints.
2.  `docs/TRADING_GLOSSARY.md` --- beginner-level definitions; explain
    new trading terms in plain English.
3.  `docs/EXCHANGE_API_RULES.md` --- official API endpoints, environment
    separation, rate limits, WebSocket behavior, and authentication.
4.  `docs/STRATEGY_SPEC.md` --- exact, versioned strategy rules; the
    coder must not invent or silently alter them.
5.  `docs/RISK_POLICY.md` --- hard risk limits and conditions that must
    block trades.
6.  `docs/BACKTESTING_POLICY.md` --- no look-ahead, chronological
    splits, fees, slippage, and benchmark rules.
7.  `docs/SECURITY_POLICY.md` --- secret handling, least privilege, no
    withdrawal permissions, and no secret output.
8.  `docs/TESTING_POLICY.md` --- required unit, integration, restart,
    outage, and accounting tests.
9.  `docs/OPERATIONS_RUNBOOK.md` --- how to start, stop, restart,
    inspect health, and recover the system.
10. `docs/DECISIONS.md` --- architecture decisions and reasons, to
    prevent the model from repeatedly changing the design.

## Copy-ready master instruction for your AI coding model

> You are the senior Python engineer and quantitative-trading systems
> tutor for this repository. The user is a complete beginner in trading
> and exchange platforms. Explain trading concepts in plain English
> before using unexplained jargon.
>
> Build a research and paper-trading system, not a profit-promise
> machine. The first release is BTC/USDT spot-only, one strategy, live
> public market data, and simulated execution. Do not implement live
> order execution, leverage, margin, futures, borrowing, deposits,
> withdrawals, or wallet custody in the MVP.
>
> Follow the official exchange API documentation. Never invent
> endpoints, parameters, rate limits, or account requirements. If
> documentation is unclear or may have changed, identify the uncertainty
> and ask for the exact official reference rather than guessing.
>
> Keep market data, features, strategy, risk management, portfolio
> accounting, execution adapters, persistence, and reporting as separate
> modules. The strategy proposes trades; the risk manager can reject
> them; only the paper executor can create MVP fills.
>
> No strategy may use future data. Use closed candles for close-based
> signals. Store timestamps in UTC. Detect stale, missing, duplicated,
> and out-of-order data. Reconnect safely and repair gaps.
>
> Every simulated fill must account for bid/ask spread, fees, slippage,
> order type, partial fills where modelled, and exchange
> precision/minimum-notional constraints. Clearly label assumptions and
> never present gross P&L as net P&L.
>
> Persist orders, fills, decisions, balances, configuration versions,
> and errors. Make order processing idempotent. On restart, reconcile
> state before taking new action. If data is stale, account state is
> uncertain, or an API error could cause duplicate orders, block new
> entries.
>
> Enforce the risk policy in code, not only in prompts. Provide an
> emergency stop. Never let an LLM bypass risk controls or directly
> place orders.
>
> Do not silently change strategy rules or optimize parameters against
> the test set. Every change must be documented, versioned, tested, and
> evaluated on untouched out-of-sample data.
>
> Work milestone by milestone. Before coding, explain the goal, files to
> change, risks, and acceptance tests. Make the smallest coherent
> change. Add tests. Run tests. Summarize what changed, what passed,
> what remains uncertain, and exact next steps. Do not claim a milestone
> is complete unless its acceptance checklist passes.
>
> Treat API keys and secrets as sensitive. Never print them, commit
> them, request withdrawal permissions, or place them in prompts. Keep
> demo and live configurations separate. Live mode must remain disabled
> unless a future, explicit human-approved scope authorizes it.

------------------------------------------------------------------------

# 11. How to use this roadmap with your AI coder

Do not ask the model to generate the entire bot in one prompt. That
encourages fabricated API details and untested code.

For every milestone, use this workflow:

1.  Ask it to read `AGENTS.md` and the relevant policy documents.
2.  Ask it to explain the milestone in beginner-friendly terms.
3.  Ask it to inspect the current project and list the exact files it
    plans to create/change.
4.  Ask it to cite the official API documentation for any
    exchange-specific behavior.
5.  Ask it to implement only that milestone.
6.  Ask it to add tests, including failure cases.
7.  Ask it to run the tests and show actual results.
8.  Review the diff before accepting it.
9.  Update the milestone checklist only after the acceptance gate
    passes.
10. Commit the working milestone to Git before moving on.

A useful task prompt:

> Implement Milestone \[N\] only. First inspect the repository and
> relevant docs. Do not modify unrelated modules. Explain the design in
> beginner-friendly terms, list files to change, identify risks, and
> define tests before coding. Use official documentation for all
> exchange API behavior. Implement the smallest complete change, run the
> tests, and report exact results. Do not claim completion if tests fail
> or requirements remain unverified.

------------------------------------------------------------------------

# 12. Overnight operation checklist

Before leaving the bot running:

-   [ ] It is explicitly in `simulator` or `exchange_demo` mode.
-   [ ] Live trading is disabled.
-   [ ] Correct symbol and spot market are selected.
-   [ ] Latest market-data timestamp is fresh.
-   [ ] WebSocket heartbeat/reconnect works.
-   [ ] Missing candles are detected.
-   [ ] SQLite database is writable and backed up.
-   [ ] Logs are rotating and do not contain secrets.
-   [ ] Risk limits are loaded and validated.
-   [ ] Daily loss stop and emergency stop work.
-   [ ] Restart recovery has been tested.
-   [ ] Dashboard shows data-feed and bot health.
-   [ ] Computer power/sleep settings will not suspend the process.
-   [ ] You know how to stop the process manually.

For the first several nights, review it each morning and inspect every
trade. "Autonomous" must not mean "unobserved and trusted."

------------------------------------------------------------------------

# 13. Official links and documentation

Use official documentation as the source of truth; tutorials and
AI-generated examples can become outdated.

-   Bybit V5 API introduction:
    https://bybit-exchange.github.io/docs/v5/intro
-   Bybit Demo Trading: https://bybit-exchange.github.io/docs/v5/demo
-   Bybit WebSocket connection:
    https://bybit-exchange.github.io/docs/v5/ws/connect
-   Binance Spot Test Network:
    https://developers.binance.com/docs/binance-spot-api-docs/testnet
-   CCXT manual: https://docs.ccxt.com/
-   Python tutorial: https://docs.python.org/3/tutorial/
-   pandas documentation: https://pandas.pydata.org/docs/
-   Backtesting.py: https://kernc.github.io/backtesting.py/
-   pytest: https://docs.pytest.org/
-   SEC Philippines advisories:
    https://www.sec.gov.ph/investor-education-and-information/advisories/
-   BSP: https://www.bsp.gov.ph/

------------------------------------------------------------------------

# 14. Final roadmap summary

  -----------------------------------------------------------------------
                  Milestone Result                       Can paper trade?
  ------------------------- ------------------- -------------------------
                          0 Understand exchange                  Manually
                            and trading basics  

                          1 Safe Python project                        No
                            foundation          

                          2 Live market-data                    Data only
                            collector           

                          3 Indicator/feature                Signals only
                            engine              

                          4 One explicit                     Signals only
                            strategy            

                          5 Historical              Historical simulation
                            backtesting         

                          6 Internal live-data                    **Yes**
                            paper simulator     

                          7 Monitored,           **Yes --- MVP achieved**
                            persistent          
                            paper-trading MVP   

                          8 Exchange demo API                         Yes
                            integration         

                          9 Order-flow features                       Yes

                         10 Regime detection                          Yes

                         11 News/sentiment                            Yes

                         12 Machine-learning                          Yes
                            research            

                     Future Separately reviewed   Real funds; not part of
                            live execution                            MVP
  -----------------------------------------------------------------------

## The most important takeaway

**Your first real achievement is Milestone 7, not making your first
deposit.**

You can build, test, and run the complete MVP without depositing ₱500,
creating a blockchain wallet, paying for AI APIs, or purchasing a VPS.
Only consider real-money trading after the paper system has demonstrated
reliable operation, honest net-of-cost performance, and acceptable
drawdown---and even then, it may be better not to trade if ₱500 is money
you need for essentials.
