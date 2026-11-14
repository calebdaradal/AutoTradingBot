"""Bybit PUBLIC market-data client (REST). No API key is used or needed.

Docs: https://bybit-exchange.github.io/docs/v5/market/kline
      https://bybit-exchange.github.io/docs/v5/market/tickers
"""
import time

import requests

from .. import log
from ..models import Candle, DataQualityError, Quote, interval_ms, now_ms, validate_candle

KLINE_LIMIT = 1000  # documented maximum per request


class BybitError(Exception):
    pass


class BybitPublic:
    def __init__(self, rest_url: str, category: str = "spot", symbol: str = "BTCUSDT", session=None):
        self.url = rest_url.rstrip("/")
        self.category = category
        self.symbol = symbol
        self.http = session or requests.Session()
        self.last_server_ms: int | None = None

    def _get(self, path: str, params: dict, retries: int = 4):
        delay = 1.0
        for attempt in range(1, retries + 1):
            try:
                r = self.http.get(self.url + path, params=params, timeout=15)
                if r.status_code in (403, 429):  # rate-limited: back off
                    raise BybitError(f"HTTP {r.status_code} (rate limit / blocked)")
                r.raise_for_status()
                body = r.json()
                if body.get("retCode") != 0:
                    raise BybitError(f"Bybit error {body.get('retCode')}: {body.get('retMsg')}")
                self.last_server_ms = int(body.get("time", now_ms()))
                return body["result"]
            except (requests.RequestException, BybitError, ValueError) as e:
                if attempt == retries:
                    raise BybitError(f"{path} failed after {retries} tries: {e}") from e
                log.warn(f"Bybit request problem ({e}); retrying in {delay:.0f}s")
                time.sleep(delay)
                delay = min(delay * 2, 30)

    def fetch_klines(self, interval: int, start_ms=None, end_ms=None, limit=KLINE_LIMIT):
        """Return CLOSED candles, oldest first. The still-forming candle is dropped."""
        params = {"category": self.category, "symbol": self.symbol, "interval": str(interval), "limit": limit}
        if start_ms is not None:
            params["start"] = int(start_ms)
        if end_ms is not None:
            params["end"] = int(end_ms)
        result = self._get("/v5/market/kline", params)
        server_now = self.last_server_ms or now_ms()
        out, bad = {}, 0
        for row in result.get("list", []):
            try:
                c = Candle(int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]))
                validate_candle(c)
            except (ValueError, IndexError, DataQualityError) as e:
                bad += 1
                log.error(f"Skipped malformed candle from Bybit: {e}")
                continue
            if c.start + interval_ms(interval) <= server_now:  # fully closed only
                out[c.start] = c
        return [out[k] for k in sorted(out)]

    def fetch_history(self, interval: int, since_ms: int, until_ms: int | None = None, progress=None):
        """Download all closed candles from since_ms up to until_ms (pages backwards)."""
        until = until_ms or now_ms()
        collected: dict[int, Candle] = {}
        end = until
        while end > since_ms:
            batch = self.fetch_klines(interval, start_ms=since_ms, end_ms=end)
            if not batch:
                break
            for c in batch:
                collected[c.start] = c
            oldest = batch[0].start
            if progress:
                progress(len(collected))
            if oldest <= since_ms or oldest >= end:
                break
            end = oldest - 1
            time.sleep(0.12)  # stay well under rate limits
        return [collected[k] for k in sorted(collected)]

    def fetch_quote(self) -> Quote:
        result = self._get("/v5/market/tickers", {"category": self.category, "symbol": self.symbol})
        item = result["list"][0]
        bid, ask = float(item["bid1Price"]), float(item["ask1Price"])
        if bid <= 0 or ask <= 0 or ask < bid:
            raise DataQualityError(f"bad bid/ask: {bid}/{ask}")
        return Quote(bid, ask, now_ms())
