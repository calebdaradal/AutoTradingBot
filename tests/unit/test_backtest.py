"""Backtester tests. We hand-build tiny price stories so every rule can be checked exactly.

Story used by most tests (prices are made up, costs are the real config costs):
  bar 0: the indicators say BUY (decision is made at the CLOSE of this bar)
  bar 1: the buy must happen at bar 1's OPEN
  bar 2: something happens (stop hit, target hit, gap down, nothing...)
"""
import pytest

from trading_bot.backtest import Result, run_backtest, split_ranges, with_overrides
from trading_bot.features import Feature
from trading_bot.models import Candle
from trading_bot.portfolio import fill_price

STEP = 900_000
T0 = 1_700_000_000_000


def story(bars):
    """bars = [(open, high, low, close), ...] -> candles + 'everything says BUY' features."""
    entry, feats = [], []
    for i, (o, h, l, c) in enumerate(bars):
        start = T0 + i * STEP
        entry.append(Candle(start, o, h, l, c, 2.0))
        feats.append(Feature(start, start + STEP, o, h, l, c, 2.0, rsi=60.0, atr=1.0, vol_ma=1.0,
                             trend_fast=2.0, trend_slow=1.0))
    return entry, feats


def run(cfg, bars, equity=1000.0):
    entry, feats = story(bars)
    return run_backtest(entry, [], cfg, equity, feats=feats), entry


BAR0 = (100, 100, 100, 100)
BAR1 = (101, 102, 100, 101)


def test_buy_happens_at_next_candle_open_not_signal_candle(cfg):
    res, entry = run(cfg, [BAR0, BAR1, (101, 101, 101, 101)])
    t = res.trades[0]
    assert t["entry_ms"] == entry[1].start                      # not bar 0
    assert t["entry"] == pytest.approx(fill_price("BUY", 101, cfg.costs))   # bar 1 open + costs


def test_stop_wins_when_one_candle_touches_stop_and_target(cfg):
    res, _ = run(cfg, [BAR0, BAR1, (101, 110, 90, 101)])        # candle 2 touches BOTH levels
    t = res.trades[0]
    assert t["reason"] == "stop-loss"
    assert t["exit"] == pytest.approx(fill_price("SELL", t["entry"] - 2.0, cfg.costs))
    assert t["net"] < 0


def test_stop_gap_fills_at_the_worse_open_price(cfg):
    res, _ = run(cfg, [BAR0, BAR1, (95, 96, 94, 95)])           # opens far BELOW the stop
    t = res.trades[0]
    assert t["reason"] == "stop-loss"
    assert t["exit"] == pytest.approx(fill_price("SELL", 95, cfg.costs))


def test_target_hit_fills_at_target(cfg):
    res, _ = run(cfg, [BAR0, BAR1, (101, 106, 101, 105)])
    t = res.trades[0]
    assert t["reason"] == "target reached"
    assert t["exit"] == pytest.approx(fill_price("SELL", t["entry"] + 3.0, cfg.costs))
    assert t["net"] > 0


def test_open_trade_is_closed_at_end_of_period(cfg):
    res, _ = run(cfg, [BAR0, BAR1, (101, 101.5, 100.5, 101)])
    assert res.trades[-1]["reason"] == "end of test period"
    assert res.end_equity == pytest.approx(1000 + res.net_pnl)  # all money is cash again, nothing left open


def test_same_inputs_give_same_results(cfg):
    bars = [BAR0, BAR1, (101, 106, 101, 105)]
    a, _ = run(cfg, bars)
    b, _ = run(cfg, bars)
    assert a.metrics() == b.metrics()
    assert a.trades == b.trades


def test_higher_costs_lower_the_result(cfg):
    bars = [BAR0, BAR1, (101, 106, 101, 105)]
    cheap, _ = run(cfg, bars)
    entry, feats = story(bars)
    pricey = run_backtest(entry, [], with_overrides(cfg, cost_mult=3.0), 1000.0, feats=feats)
    assert pricey.net_pnl < cheap.net_pnl
    assert pricey.fees_paid > cheap.fees_paid


def test_trade_records_best_and_worst_price_and_indicator_snapshot(cfg):
    res, _ = run(cfg, [BAR0, BAR1, (101, 106, 101, 105)])
    t = res.trades[0]
    assert t["mfe"] == pytest.approx(106 / t["entry"] - 1)      # best price reached vs entry
    assert t["mae"] == pytest.approx(100 / t["entry"] - 1)      # worst price reached vs entry
    assert t["signal"]["rsi"] == 60.0


def test_split_is_chronological_and_covers_everything(cfg):
    r = split_ranges(1000, cfg)
    assert r["train"] == (0, 500)
    assert r["validation"] == (500, 750)
    assert r["test"] == (750, 1000)


# ---------- performance numbers, checked on hand-made trades ----------

def make_result(nets, curve=None, start_equity=100.0):
    trades = [{"net": n, "gross": n, "qty": 1.0, "entry": 100.0, "exit": 110.0} for n in nets]
    return Result("t", 0, 5 * 86_400_000, start_equity, start_equity + sum(nets), trades,
                  curve or [], 0.0, 100, 50, 1.5)


def test_trade_statistics():
    r = make_result([2, -1, -3, -1, 4])
    assert r.expectancy == pytest.approx(0.2)
    assert r.avg_win == pytest.approx(3.0)
    assert r.avg_loss == pytest.approx(-5 / 3)
    assert r.largest_win == 4 and r.largest_loss == -3
    assert r.longest_losing_streak == 3
    assert r.profit_factor == pytest.approx(6 / 5)
    assert r.win_rate == pytest.approx(0.4)
    assert r.turnover == pytest.approx(5 * 210 / 100)


def test_no_trades_gives_zeros_not_crashes():
    r = make_result([])
    assert (r.expectancy, r.avg_win, r.avg_loss, r.longest_losing_streak, r.win_rate) == (0, 0, 0, 0, 0)
    assert r.metrics()["trades"] == 0


def test_profit_factor_with_no_losses_is_saved_as_none():
    r = make_result([1, 2])
    assert r.profit_factor == float("inf")
    assert r.metrics()["profit_factor"] is None                 # JSON cannot store infinity


def test_drawdown_depth_and_duration():
    day = 86_400_000
    curve = [(0, 100), (1 * day, 110), (2 * day, 99), (3 * day, 105), (4 * day, 111)]
    r = make_result([11], curve)
    assert r.max_drawdown == pytest.approx(1 - 99 / 110)
    assert r.longest_drawdown_days == pytest.approx(2.0)        # from the day-1 peak until day-3 (still below)


def test_summary_lines_mention_new_numbers():
    text = "\n".join(make_result([2, -1]).summary_lines())
    assert "losing streak" in text and "Avg per trade" in text
