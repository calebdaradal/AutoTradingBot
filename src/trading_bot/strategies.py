"""The one and only strategy: trend_momentum v1.0  (long-only spot, BTC/USDT).

Plain-language rules
  BUY when ALL are true (checked when a 15-minute candle CLOSES):
    1. Bigger picture is UP: 1-hour EMA20 is above 1-hour EMA50.
    2. Momentum is healthy: RSI between rsi_min and rsi_max (not weak, not overheated).
    3. Market is active: volume at least volume_mult x its recent average.
    4. Market is neither dead nor wild: ATR (swing size) between atr_pct_min and atr_pct_max of price.
    5. We are not holding already, not over the daily trade limit, not in the post-trade cooldown.
  SELL when ANY is true:
    * Stop-loss hit (price fell stop_atr_mult x ATR below entry)  -> limits the damage
    * Target hit (price rose target_atr_mult x ATR above entry)   -> locks in the gain
    * Held longer than max_hold_bars candles                       -> don't wait forever
    * Bigger-picture trend turned down                             -> the reason to hold is gone

Every evaluation returns human-readable reasons so the journal explains each decision.
"""
from dataclasses import dataclass, field

from .features import Feature

BUY, SELL, HOLD = "BUY", "SELL", "HOLD"


@dataclass
class Position:
    entry_price: float
    qty: float
    stop: float
    target: float
    entry_start: int      # start time (ms) of the candle that produced the entry signal
    bars_held: int = 0


@dataclass
class Context:
    """Facts the strategy needs that are not in the candle itself."""
    trades_today: int = 0
    bars_since_exit: int = 10_000


@dataclass
class Decision:
    action: str
    reasons: list = field(default_factory=list)
    details: dict = field(default_factory=dict)


class TrendMomentum:
    def __init__(self, s):
        self.s = s
        self.version = f"{s.name}-{s.version}"

    def evaluate(self, f: Feature, pos: Position | None, ctx: Context) -> Decision:
        s = self.s
        if not f.ready:
            return Decision(HOLD, ["warming up: not enough history for indicators"])
        details = {"close": f.close, "rsi": round(f.rsi, 2), "atr": round(f.atr, 2),
                   "trend_fast": round(f.trend_fast, 2), "trend_slow": round(f.trend_slow, 2),
                   "volume": f.volume, "vol_ma": round(f.vol_ma, 4)}
        if pos is not None:
            return self._evaluate_exit(f, pos, details)
        why = []
        if not f.trend_fast > f.trend_slow:
            why.append("1h trend not up")
        if not s.rsi_min <= f.rsi <= s.rsi_max:
            why.append(f"RSI {f.rsi:.1f} outside {s.rsi_min}-{s.rsi_max}")
        if f.volume < s.volume_mult * f.vol_ma:
            why.append("volume below average")
        atr_pct = f.atr / f.close
        if atr_pct < s.atr_pct_min:
            why.append("market too quiet")
        if atr_pct > s.atr_pct_max:
            why.append("market too wild")
        if ctx.trades_today >= s.max_trades_per_day:
            why.append("daily trade limit reached")
        if ctx.bars_since_exit < s.cooldown_bars:
            why.append("cooling down after last trade")
        if why:
            return Decision(HOLD, why, details)
        details["stop"] = f.close - s.stop_atr_mult * f.atr
        details["target"] = f.close + s.target_atr_mult * f.atr
        return Decision(BUY, ["all entry conditions met"], details)

    def _evaluate_exit(self, f: Feature, pos: Position, details) -> Decision:
        s = self.s
        if f.close <= pos.stop:
            return Decision(SELL, ["stop-loss"], details)
        if f.close >= pos.target:
            return Decision(SELL, ["target reached"], details)
        if pos.bars_held >= s.max_hold_bars:
            return Decision(SELL, ["held too long"], details)
        if f.trend_fast < f.trend_slow:
            return Decision(SELL, ["1h trend turned down"], details)
        return Decision(HOLD, ["holding: no exit condition met"], details)

    def make_position(self, entry_price: float, qty: float, atr_value: float, entry_start: int) -> Position:
        s = self.s
        return Position(entry_price, qty, entry_price - s.stop_atr_mult * atr_value,
                        entry_price + s.target_atr_mult * atr_value, entry_start)

    @staticmethod
    def intrabar_exit(low: float, high: float, pos: Position):
        """Did price touch the stop or target INSIDE a candle? Stop wins if both (pessimistic)."""
        if low <= pos.stop:
            return "stop-loss", pos.stop
        if high >= pos.target:
            return "target reached", pos.target
        return None
