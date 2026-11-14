"""Backtester: replays the strategy over past candles using the SAME risk and account rules as the
paper bot, with fees + spread + slippage included.

Honest-testing rules built in:
  * A signal appears when a candle CLOSES; the trade happens at the NEXT candle's open (no peeking).
  * If a candle touches both stop and target, the stop is assumed to hit first (pessimistic).
  * Data is split in time: train (learn) / validation (check) / test (final exam, look once).
  * Compared against "buy and hold" (just buy at the start and wait) and "do nothing".
"""
import copy
from dataclasses import dataclass, field
from types import SimpleNamespace

from .features import build_features
from .portfolio import OrderRejected, Portfolio, fill_price
from .risk import RiskManager, utc_day
from .strategies import BUY, SELL, Context, TrendMomentum


@dataclass
class Result:
    label: str
    start_ms: int
    end_ms: int
    start_equity: float
    end_equity: float
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)   # (ts_ms, equity)
    buy_hold_return: float = 0.0
    bars: int = 0
    bars_in_market: int = 0
    fees_paid: float = 0.0
    blocked: dict = field(default_factory=dict)

    # ---- headline numbers ----
    @property
    def net_return(self):
        return self.end_equity / self.start_equity - 1

    @property
    def gross_pnl(self):
        return sum(t["gross"] for t in self.trades)

    @property
    def net_pnl(self):
        return sum(t["net"] for t in self.trades)

    @property
    def max_drawdown(self):
        peak, worst = self.start_equity, 0.0
        for _, e in self.equity_curve:
            peak = max(peak, e)
            worst = max(worst, 1 - e / peak)
        return worst

    @property
    def win_rate(self):
        return sum(t["net"] > 0 for t in self.trades) / len(self.trades) if self.trades else 0.0

    @property
    def profit_factor(self):
        wins = sum(t["net"] for t in self.trades if t["net"] > 0)
        loss = -sum(t["net"] for t in self.trades if t["net"] < 0)
        return float("inf") if loss == 0 and wins > 0 else (wins / loss if loss else 0.0)

    @property
    def exposure(self):
        return self.bars_in_market / self.bars if self.bars else 0.0

    # ---- extra honesty numbers (plain meaning in the comments) ----
    @property
    def avg_win(self):          # average profit of a winning trade (USDT)
        w = [t["net"] for t in self.trades if t["net"] > 0]
        return sum(w) / len(w) if w else 0.0

    @property
    def avg_loss(self):         # average loss of a losing trade (USDT, negative number)
        l = [t["net"] for t in self.trades if t["net"] < 0]
        return sum(l) / len(l) if l else 0.0

    @property
    def expectancy(self):       # average result per trade after costs (USDT). Must be > 0 to have an edge
        return self.net_pnl / len(self.trades) if self.trades else 0.0

    @property
    def largest_win(self):
        return max((t["net"] for t in self.trades), default=0.0)

    @property
    def largest_loss(self):
        return min((t["net"] for t in self.trades), default=0.0)

    @property
    def longest_losing_streak(self):   # most losing trades in a row
        best = cur = 0
        for t in self.trades:
            cur = cur + 1 if t["net"] < 0 else 0
            best = max(best, cur)
        return best

    @property
    def longest_drawdown_days(self):   # longest time spent below a previous peak
        peak, peak_ts, worst = self.start_equity, self.start_ms, 0
        for ts, e in self.equity_curve:
            if e >= peak:
                peak, peak_ts = e, ts
            else:
                worst = max(worst, ts - peak_ts)
        return worst / 86_400_000

    @property
    def turnover(self):         # total money bought + sold, as a multiple of the starting balance
        v = sum(t["qty"] * (t["entry"] + t["exit"]) for t in self.trades)
        return v / self.start_equity if self.start_equity else 0.0

    @property
    def avg_mfe(self):          # on average, how far a trade went IN our favour before it ended
        m = [t["mfe"] for t in self.trades if "mfe" in t]
        return sum(m) / len(m) if m else 0.0

    @property
    def avg_mae(self):          # on average, how far a trade went AGAINST us before it ended (negative)
        m = [t["mae"] for t in self.trades if "mae" in t]
        return sum(m) / len(m) if m else 0.0

    def metrics(self) -> dict:
        """All headline numbers as plain numbers (safe to save as JSON; 'infinite' becomes None)."""
        pf = self.profit_factor
        return {
            "days": round((self.end_ms - self.start_ms) / 86_400_000, 2), "trades": len(self.trades),
            "start_equity": self.start_equity, "end_equity": self.end_equity,
            "net_return": self.net_return, "buy_hold_return": self.buy_hold_return,
            "gross_pnl": self.gross_pnl, "net_pnl": self.net_pnl, "fees_paid": self.fees_paid,
            "max_drawdown": self.max_drawdown, "longest_drawdown_days": self.longest_drawdown_days,
            "win_rate": self.win_rate, "profit_factor": None if pf == float("inf") else pf,
            "expectancy": self.expectancy, "avg_win": self.avg_win, "avg_loss": self.avg_loss,
            "largest_win": self.largest_win, "largest_loss": self.largest_loss,
            "longest_losing_streak": self.longest_losing_streak, "turnover": self.turnover,
            "exposure": self.exposure, "avg_mfe": self.avg_mfe, "avg_mae": self.avg_mae,
            "blocked": dict(self.blocked),
        }

    def summary_lines(self):
        days = max((self.end_ms - self.start_ms) / 86_400_000, 1e-9)
        return [
            f"[{self.label}] {days:.0f} days, {len(self.trades)} trades",
            f"  Bot result (after costs): {self.net_return:+.2%}   | Buy-and-hold: {self.buy_hold_return:+.2%}   | Do-nothing: +0.00%",
            f"  Profit before costs: {self.gross_pnl:+.3f} USDT | after costs: {self.net_pnl:+.3f} USDT | fees paid: {self.fees_paid:.3f} USDT",
            f"  Worst drop from a peak: {self.max_drawdown:.2%} | win rate: {self.win_rate:.0%} | profit factor: {self.profit_factor:.2f} | time in market: {self.exposure:.0%}",
            f"  Avg per trade: {self.expectancy:+.4f} USDT | avg win {self.avg_win:+.4f} | avg loss {self.avg_loss:+.4f} | "
            f"biggest loss {self.largest_loss:+.4f} | losing streak {self.longest_losing_streak} | "
            f"longest time under a peak: {self.longest_drawdown_days:.0f} days | turnover {self.turnover:.1f}x",
        ]


def scaled_costs(costs, mult: float):
    c = copy.deepcopy(costs)
    for k in ("taker_fee", "half_spread", "slippage"):
        setattr(c, k, getattr(costs, k) * mult)
    return c


def with_overrides(cfg, strategy: dict | None = None, cost_mult: float = 1.0):
    c = copy.deepcopy(cfg)
    for k, v in (strategy or {}).items():
        setattr(c.strategy, k, v)
    c.costs = scaled_costs(cfg.costs, cost_mult)
    return c


def split_ranges(n: int, cfg):
    a = int(n * cfg.backtest.train_frac)
    b = a + int(n * cfg.backtest.validation_frac)
    return {"train": (0, a), "validation": (a, b), "test": (b, n)}


def run_backtest(entry, trend, cfg, start_equity: float, lo: int = 0, hi: int | None = None,
                 label: str = "full", feats=None) -> Result:
    hi = len(entry) if hi is None else hi
    feats = feats or build_features(entry, trend, cfg.strategy, cfg.data.entry_interval, cfg.data.trend_interval)
    strat = TrendMomentum(cfg.strategy)
    pf = Portfolio(start_equity, cfg.costs, cfg.exchange_rules)
    risk = RiskManager(cfg.risk, cfg.exchange_rules)
    res = Result(label, entry[lo].start, entry[hi - 1].start, start_equity, start_equity)

    pos, pending, ctx_day, trades_today, bars_since_exit = None, None, None, 0, 10_000
    entry_info = {}

    def close_position(bar_ts, price, reason):
        nonlocal pos, bars_since_exit
        fill = pf.sell(pf.base, price)
        res.fees_paid += fill.fee
        res.trades.append({
            "entry_ms": entry_info["ts"], "exit_ms": bar_ts, "entry": entry_info["price"], "exit": fill.price,
            "qty": fill.qty, "gross": fill.realized_gross, "net": fill.realized_net, "reason": reason,
            "bars": pos.bars_held,
            "mfe": entry_info["hi"] / entry_info["price"] - 1,   # best the price got vs our entry
            "mae": entry_info["lo"] / entry_info["price"] - 1,   # worst the price got vs our entry
            "signal": entry_info.get("signal"),                  # what the indicators said at the decision
        })
        risk.record_trade_result(fill.realized_net, bar_ts)
        pos, bars_since_exit = None, 0

    for i in range(lo, hi):
        bar, f = entry[i], feats[i]
        day = utc_day(bar.start)
        if day != ctx_day:
            ctx_day, trades_today = day, 0

        # 1) carry out the order decided at the previous candle's close, at this candle's open
        if pending:
            side, info = pending
            pending = None
            try:
                if side == BUY:
                    price = fill_price("BUY", bar.open, cfg.costs)
                    stop = price - cfg.strategy.stop_atr_mult * info["atr"]
                    qty = risk.size(pf.equity(bar.open), pf.cash, price, stop, cfg.costs.taker_fee)
                    fill = pf.buy(qty, price)
                    res.fees_paid += fill.fee
                    pos = strat.make_position(fill.price, fill.qty, info["atr"], bar.start)
                    entry_info = {"ts": bar.start, "price": fill.price, "hi": fill.price, "lo": fill.price,
                                  "signal": info.get("signal")}
                    risk.record_order()
                    trades_today += 1
                elif pos:
                    close_position(bar.start, fill_price("SELL", bar.open, cfg.costs), info["reason"])
                    risk.record_order()
            except OrderRejected as e:
                res.blocked[str(e)] = res.blocked.get(str(e), 0) + 1

        # 2) did price hit the stop/target during this candle?
        if pos:
            entry_info["hi"] = max(entry_info["hi"], bar.high)
            entry_info["lo"] = min(entry_info["lo"], bar.low)
            hit = strat.intrabar_exit(bar.low, bar.high, pos)
            if hit:
                reason, level = hit
                level = min(level, bar.open) if reason == "stop-loss" else max(level, bar.open)  # gaps
                close_position(bar.start, fill_price("SELL", level, cfg.costs), reason)

        # 3) candle closed: record equity, then decide what to do next
        mark = bar.close
        eq = pf.equity(mark)
        pf.update_peak(mark)
        res.equity_curve.append((bar.start, eq))
        res.bars += 1
        if pos:
            res.bars_in_market += 1
            pos.bars_held += 1
        bars_since_exit += 1 if not pos else 0

        decision = strat.evaluate(f, pos, Context(trades_today, bars_since_exit))
        if decision.action == BUY:
            ok, why = risk.check_entry(cfg.symbol, eq, pf.peak_equity, f.close_ms)
            if ok:
                pending = (BUY, {"atr": f.atr, "signal": {
                    "rsi": round(f.rsi, 2), "atr_pct": round(f.atr / f.close, 5),
                    "volume_ratio": round(f.volume / f.vol_ma, 3) if f.vol_ma else None,
                    "trend_gap_pct": round(f.trend_fast / f.trend_slow - 1, 5)}})
            else:
                for w in why:
                    res.blocked[w] = res.blocked.get(w, 0) + 1
        elif decision.action == SELL:
            pending = (SELL, {"reason": decision.reasons[0]})

    if pos:  # close the books at the end so results are comparable
        last = entry[hi - 1]
        close_position(last.start, fill_price("SELL", last.close, cfg.costs), "end of test period")
    res.end_equity = pf.equity(entry[hi - 1].close)
    res.equity_curve[-1] = (res.equity_curve[-1][0], res.end_equity)
    res.buy_hold_return = entry[hi - 1].close / entry[lo].open - 1
    return res
