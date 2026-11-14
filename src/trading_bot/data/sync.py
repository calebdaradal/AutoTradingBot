"""Download history and repair gaps so the database has a complete, clean candle record."""
from .. import log
from ..models import interval_ms, now_ms


def sync_history(client, db, symbol: str, interval: int, days: float) -> int:
    """Download the last `days` days of closed candles. Safe to re-run (duplicates ignored)."""
    since = now_ms() - int(days * 86_400_000)
    candles = client.fetch_history(interval, since)
    new = db.save_candles(symbol, interval, candles)
    log.ok(f"{interval}m history: {len(candles)} downloaded, {new} new")
    return new


def repair_gaps(client, db, symbol: str, interval: int) -> int:
    """Find missing candles inside what we have and refetch them."""
    gaps = db.find_gaps(symbol, interval)
    if not gaps:
        log.ok(f"{interval}m candles: no gaps")
        return 0
    log.warn(f"{interval}m candles: {len(gaps)} missing, repairing")
    fixed = 0
    step = interval_ms(interval)
    i = 0
    while i < len(gaps):  # refetch each run of consecutive missing candles
        j = i
        while j + 1 < len(gaps) and gaps[j + 1] - gaps[j] == step:
            j += 1
        batch = client.fetch_klines(interval, start_ms=gaps[i], end_ms=gaps[j] + step - 1)
        fixed += db.save_candles(symbol, interval, batch)
        i = j + 1
    left = len(db.find_gaps(symbol, interval))
    (log.ok if left == 0 else log.warn)(f"{interval}m gap repair: fixed {fixed}, still missing {left}")
    return fixed


def quality_report(db, symbol: str, interval: int) -> dict:
    a, b, n = db.candle_bounds(symbol, interval)
    gaps = len(db.find_gaps(symbol, interval)) if n else 0
    return {"interval": interval, "count": n, "first_ms": a, "last_ms": b, "gaps": gaps}
