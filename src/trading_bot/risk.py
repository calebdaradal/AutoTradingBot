"""Risk manager: the bot's safety officer. It can say NO to any new buy. It never blocks a sell
(getting out of a position is always allowed).

Checks before every buy:
  symbol allowed - trading switched on - kill switch off - data fresh - spread (buy/sell price gap)
  small enough - daily loss limit - drawdown stop (fall from best-ever balance) - max orders/day
  - cooldown after a losing streak
"""
from datetime import datetime, timezone

from .portfolio import round_down


def utc_day(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


class RiskManager:
    def __init__(self, r, rules):
        self.r, self.rules = r, rules
        self.day = None
        self.day_start_equity = None
        self.orders_today = 0
        self.consec_losses = 0
        self.cooldown_until_ms = 0
        self.halted: str | None = None   # set by drawdown stop; needs a human to clear

    # ---- persistence (so a restart remembers) ----
    def to_dict(self):
        return {k: getattr(self, k) for k in
                ("day", "day_start_equity", "orders_today", "consec_losses", "cooldown_until_ms", "halted")}

    def load(self, d: dict):
        for k, v in (d or {}).items():
            setattr(self, k, v)

    # ---- bookkeeping ----
    def roll_day(self, ts_ms: int, equity: float):
        d = utc_day(ts_ms)
        if d != self.day:
            self.day, self.day_start_equity, self.orders_today = d, equity, 0

    def record_order(self):
        self.orders_today += 1

    def record_trade_result(self, net_pnl: float, ts_ms: int):
        if net_pnl < 0:
            self.consec_losses += 1
            if self.consec_losses >= self.r.max_consecutive_losses:
                self.cooldown_until_ms = ts_ms + int(self.r.loss_cooldown_hours * 3_600_000)
                self.consec_losses = 0
        else:
            self.consec_losses = 0

    # ---- decisions ----
    def check_entry(self, symbol, equity, peak_equity, ts_ms, quote=None, data_stale=False,
                    trading_enabled=True, kill_switch=False):
        """Returns (allowed, reasons_if_blocked)."""
        r, why = self.r, []
        self.roll_day(ts_ms, equity)
        if symbol not in r.allowed_symbols:
            why.append(f"{symbol} not in allowed list")
        if not trading_enabled:
            why.append("trading disabled in config")
        if kill_switch:
            why.append("emergency stop is ON")
        if data_stale:
            why.append("market data is stale")
        if quote is not None and quote.spread_pct > r.max_spread_pct:
            why.append(f"spread {quote.spread_pct:.4%} too wide")
        if peak_equity > 0 and equity <= peak_equity * (1 - r.max_drawdown_pct):
            self.halted = f"drawdown stop: equity fell {r.max_drawdown_pct:.0%} from its peak"
        if self.halted:
            why.append(self.halted)
        if self.day_start_equity and equity <= self.day_start_equity * (1 - r.daily_loss_limit_pct):
            why.append("daily loss limit hit")
        if self.orders_today >= r.max_orders_per_day:
            why.append("max orders for today reached")
        if ts_ms < self.cooldown_until_ms:
            why.append("cooling down after losing streak")
        return (not why), why

    def size(self, equity: float, cash: float, price: float, stop: float, taker_fee: float) -> float:
        """How much BTC to buy: risk only risk_per_trade_pct of equity if the stop is hit,
        never more than max_position_pct of equity, and never more than the cash we have."""
        stop_dist = price - stop
        if stop_dist <= 0:
            return 0.0
        by_risk = equity * self.r.risk_per_trade_pct / stop_dist
        by_cap = equity * self.r.max_position_pct / price
        by_cash = cash / (price * (1 + taker_fee))
        return round_down(min(by_risk, by_cap, by_cash), self.rules.qty_step)
