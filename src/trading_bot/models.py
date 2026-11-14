from dataclasses import dataclass
import math
import time


def now_ms() -> int:
    return int(time.time() * 1000)


def interval_ms(minutes: int) -> int:
    return minutes * 60_000


@dataclass(frozen=True)
class Candle:
    """One price bar (OHLCV). `start` is the UTC millisecond timestamp when it opened."""
    start: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Quote:
    """Best buy price (bid) and best sell price (ask) at one moment."""
    bid: float
    ask: float
    ts_ms: int  # when WE received it (local UTC ms)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread_pct(self) -> float:
        return (self.ask - self.bid) / self.mid


class DataQualityError(Exception):
    pass


def validate_candle(c: Candle) -> None:
    """Raise DataQualityError if the candle is broken (bad numbers, impossible high/low)."""
    vals = (c.open, c.high, c.low, c.close, c.volume)
    if any(not math.isfinite(v) for v in vals):
        raise DataQualityError(f"non-finite value in candle {c.start}")
    if min(c.open, c.high, c.low, c.close) <= 0 or c.volume < 0:
        raise DataQualityError(f"non-positive price/volume in candle {c.start}")
    if c.high < max(c.open, c.close, c.low) or c.low > min(c.open, c.close, c.high):
        raise DataQualityError(f"high/low inconsistent in candle {c.start}")
