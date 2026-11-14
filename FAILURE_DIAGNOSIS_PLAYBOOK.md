# Failure Diagnosis Playbook

## Purpose

Provide a repeatable way to explain why a strategy loses money or
behaves differently from expectations.

The diagnostic engine must distinguish measured facts from possible
causes. It should rank hypotheses, show supporting evidence, and propose
controlled experiments. It must not claim causation from correlation
alone.

## 1. Required diagnostic inputs

For each trade and decision, retain where available: - strategy version
and configuration; - timestamp and candle identifiers; - market regime
labels and their definitions; - feature/indicator values at decision
time; - entry/exit reason; - intended and simulated execution prices; -
bid/ask spread; - fees and slippage; - quantity and exposure; - stop,
target, and time-exit levels; - gross and net P&L; - maximum favorable
excursion (MFE); - maximum adverse excursion (MAE); - holding
duration; - risk-manager decisions and rejections.

If an input is not currently stored, mark it as a data gap before
diagnosing.

## 2. First-level performance triage

Before changing strategy rules, verify:

1.  Is the dataset correct and complete?
2.  Are timestamps and candle-close rules correct?
3.  Is there look-ahead or data leakage?
4.  Are fees, spread, and slippage applied correctly?
5.  Are order quantities and minimum notional modeled correctly?
6.  Are positions, cash, fills, and equity reconciled?
7.  Are backtest and paper execution assumptions comparable?
8.  Are benchmark calculations correct?

If any of these fail, classify the result as **OPERATIONAL / DATA
INVALID**. Do not diagnose strategy logic using corrupted evidence.

## 3. Entry failure diagnostics

  -----------------------------------------------------------------------
  Symptom           Candidate         Evidence to       Controlled
                    explanations      inspect           experiment
  ----------------- ----------------- ----------------- -----------------
  Low win rate      Weak signal, late Entry features,   Test one
                    entry, noisy      regime,           confirmation or
                    market            subsequent price  timing change
                                      path              

  Many entries      False trend or    Trend slope,      Add a predeclared
  reverse quickly   breakout          recent range,     trend-quality
                                      volume, reversal  filter
                                      frequency         

  Entries occur     Lagging           Entry location    Compare earlier
  after most of a   confirmation      relative to       trigger while
  move                                recent range and  preserving risk
                                      trend             

  Good signals are  Filters too       Rejected-signal   Relax one filter
  skipped           restrictive       log and           and assess false
                                      subsequent price  positives
                                      path              

  Losses cluster in Trend strategy    Results segmented Test a
  sideways periods  exposed to range  by defined regime range/no-trade
                    markets                             filter

  Entries cluster   Spread/depth      Spread, volume,   Test a liquidity
  at poor liquidity unsuitable        book data if      eligibility rule
                                      available         
  -----------------------------------------------------------------------

Do not label an entry "bad" solely because it lost. Evaluate the
distribution over many trades.

## 4. Exit failure diagnostics

  ------------------------------------------------------------------------
  Symptom           Candidate         Evidence to       Controlled
                    explanations      inspect           experiment
  ----------------- ----------------- ----------------- ------------------
  Winning trades    Exit too slow or  MFE, MAE, exit    Compare a
  turn into losses  stop not          reason, price     predeclared exit
                    effective         path              rule

  Average loss much Poor payoff ratio Average win/loss, Test one
  larger than       or stop/target    tail losses       stop/target
  average win       design                              hypothesis

  Many small wins,  Tail risk or      Loss              Stress-test
  occasional large  trend reversal    distribution,     protective exit
  losses            exposure          MAE, gap/stop     behavior
                                      behavior          

  Trades remain     Time exit         Holding time and  Test alternate
  open too long     ineffective       returns by        maximum holding
                                      duration          period

  Exits cut trends  Exit reacts to    Price movement    Test a
  short             noise             after exit,       volatility-aware
                                      volatility        exit hypothesis

  Stop and target   Intrabar path     Candle high/low   Use conservative
  both touched in   unknown           and fill model    assumption or
  one candle                                            finer-grained data
  ------------------------------------------------------------------------

## 5. Market-regime failures

Use explicit, reproducible regime definitions. Do not use vague labels
assigned after seeing results.

  ---------------------------------------------------------------------------
  Symptom           Candidate         Evidence to       Controlled experiment
                    explanations      inspect           
  ----------------- ----------------- ----------------- ---------------------
  Profits           Directional       Net expectancy by Evaluate regime
  concentrated in   dependence        regime            eligibility filter
  bullish periods                                       

  Losses            Trend signal      Trade frequency   Test no-trade rule in
  concentrated in   churn             and expectancy in defined range regime
  ranges                              ranges            

  High-volatility   Stops, sizing, or ATR, spread, MAE, Test volatility-aware
  periods cause     fills unsuitable  slippage          risk or exclusion
  losses                                                

  Low-volatility    Insufficient      MFE versus total  Test minimum
  periods produce   movement after    costs             movement/volatility
  no edge           costs                               threshold

  Results vary by   Liquidity or      Time bucket       Validate only if a
  time of day       volatility        results, sample   plausible hypothesis
                    differences       sizes             exists
  ---------------------------------------------------------------------------

## 6. Execution and cost failures

  --------------------------------------------------------------------------------
  Symptom           Candidate         Evidence to inspect   Controlled experiment
                    explanations                            
  ----------------- ----------------- --------------------- ----------------------
  Backtest          Fill model too    Intended versus       Increase realism and
  positive, paper   optimistic        simulated fills       compare
  negative                                                  

  Net P&L much      Costs consume     Fee/spread/slippage   Test lower-turnover
  worse than gross  edge              attribution           rules
  P&L                                                       

  Frequent rejected Minimum size,     Rejection codes and   Correct
  orders            precision, or     order parameters      integration/modeling
                    balance                                 

  Unexpected        Idempotency or    Client order IDs and  Add regression test
  duplicate orders  state defect      order journal         and repair

  Price feed gaps   Feed/reconnect    Feed health and       Repair data
  or stale          defect            timestamps            lockout/recovery
  decisions                                                 

  Partial fills not Simulator         Fill records and      Implement realistic
  represented       limitation        remaining quantity    partial-fill model if
                                                            relevant
  --------------------------------------------------------------------------------

## 7. Risk and portfolio failures

  -----------------------------------------------------------------------
  Symptom           Candidate         Evidence to       Controlled
                    explanations      inspect           experiment
  ----------------- ----------------- ----------------- -----------------
  Excessive         Position sizing   Equity curve,     Test lower risk
  drawdown          too large or      exposure, loss    per trade without
                    strategy weak     distribution      changing signal

  Long losing       Negative edge or  Losing streak     Test regime
  streaks           clustered regimes distribution and  dependence; do
                                      regime            not assume
                                                        cooldown creates
                                                        edge

  One loss          Concentrated      Trade             Review sizing and
  dominates results exposure or tail  contribution and  protective
                    event             MAE               controls

  Daily stop        Strategy          Trigger times and Diagnose cause;
  frequently        unsuitable or     preceding trades  never simply
  activates         risk budget too                     raise limit to
                    tight                               hide losses
  -----------------------------------------------------------------------

Risk limits must not be weakened merely to improve reported returns.

## 8. Statistical and research failures

Investigate: - too few trades; - high result variance; - one or two
trades dominating total P&L; - poor walk-forward consistency; - narrow
parameter optimum; - performance collapse under modest cost stress; -
repeated tuning on the same validation/test data; - selection bias from
testing many candidates; - regime coverage gaps; - dependence between
trades that invalidates naive statistical assumptions.

A strategy can have a positive point estimate and still have
insufficient evidence. Use **INCONCLUSIVE** when sample size or
uncertainty is inadequate.

## 9. Diagnostic report format

Every diagnosis must include:

### A. Verdict

-   DATA INVALID
-   OPERATIONAL FAILURE
-   STRATEGY FAILURE
-   INCONCLUSIVE
-   NO MATERIAL FAILURE IDENTIFIED

### B. Observations

List measured facts with date ranges, trade counts, and metric values.

### C. Ranked hypotheses

For each hypothesis: - description; - supporting evidence; -
contradicting evidence; - confidence level and why; - additional data
needed.

### D. Proposed experiments

For each experiment: - hypothesis; - one controlled change; - expected
effect; - possible adverse effect; - evaluation dataset; - metrics; -
pass/fail criteria set before running.

### E. Prohibited conclusions

Do not say "the cause is X" unless the evidence supports causal
attribution. Prefer "consistent with X" or "X is a leading hypothesis."

## 10. Required discipline

-   Never delete failed results.
-   Never tune directly against the final holdout.
-   Never change several unrelated components in one experiment.
-   Never select a strategy only by highest total return.
-   Never disable risk protections to improve results.
-   Never automatically deploy a diagnosis-based modification.
