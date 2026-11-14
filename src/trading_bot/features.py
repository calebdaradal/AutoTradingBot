"""Indicators (the math that turns raw prices into signals) and the feature table.

Plain-language glossary:
  EMA    = average price that reacts faster to recent prices (trend direction)
  RSI    = 0-100 "momentum" gauge. High = recent rises dominate, low = falls dominate
  ATR    = average size of recent price swings (how jumpy the market is)
  Volume MA = average trading volume (how busy the market is)

Rule: a value is None until enough history exists (the "warm-up"). We never guess early values.
Rule: a 15m bar only sees 1h candles that were ALREADY CLOSED when the 15m bar closed (no peeking ahead).
"""
from dataclasses import dataclass

from .models import Candle, interval_ms


def sma(values, n):
    out = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(values, n):
    out = [None] * len(values)
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    prev = sum(values[:n]) / n  # seed with a simple average
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n

    def val(g, l):
        return 100.0 if l == 0 else 100 - 100 / (1 + g / l)

    out[n] = val(ag, al)
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
        out[i + 1] = val(ag, al)
    return out


def atr(candles, n=14):
    out = [None] * len(candles)
    if len(candles) < n:
        return out
    tr = [candles[0].high - candles[0].low]
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        tr.append(max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close)))
    prev = sum(tr[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(candles)):
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


@dataclass(frozen=True)
class Feature:
    """Everything the strategy needs to know at the CLOSE of one 15m candle."""
    start: int          # candle open time (ms)
    close_ms: int       # candle close time (ms)
    open: float
    high: float
    low: float
    close: float
    volume: float
    rsi: float | None
    atr: float | None
    vol_ma: float | None
    trend_fast: float | None   # 1h EMA20
    trend_slow: float | None   # 1h EMA50

    @property
    def ready(self) -> bool:
        return None not in (self.rsi, self.atr, self.vol_ma, self.trend_fast, self.trend_slow)


def build_features(entry: list[Candle], trend: list[Candle], s, entry_minutes=15, trend_minutes=60):
    """One Feature per entry candle. `s` is the strategy settings (periods)."""
    closes = [c.close for c in entry]
    r = rsi(closes, s.rsi_period)
    a = atr(entry, s.atr_period)
    vm = sma([c.volume for c in entry], s.volume_ma_period)
    tc = [c.close for c in trend]
    tf, ts = ema(tc, s.ema_fast), ema(tc, s.ema_slow)
    t_step, e_step = interval_ms(trend_minutes), interval_ms(entry_minutes)

    out, j = [], -1  # j = index of latest 1h candle already closed
    for i, c in enumerate(entry):
        close_ms = c.start + e_step
        while j + 1 < len(trend) and trend[j + 1].start + t_step <= close_ms:
            j += 1
        out.append(Feature(
            c.start, close_ms, c.open, c.high, c.low, c.close, c.volume, r[i], a[i], vm[i],
            tf[j] if j >= 0 else None, ts[j] if j >= 0 else None,
        ))
    return out
