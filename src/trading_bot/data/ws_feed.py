"""Live market feed over Bybit's PUBLIC WebSocket (a WebSocket = a phone line that stays open
so the exchange can push prices to us instantly). No API key needed.

What it does:
  * keeps the latest best buy/sell price (Quote)
  * saves every CLOSED candle to the database (15m and 1h)
  * pings every 20s (Bybit's heartbeat rule) and reconnects with growing waits if the line drops
  * reports if data goes stale (no fresh update for too long)

Docs: https://bybit-exchange.github.io/docs/v5/ws/connect
"""
import json
import random
import threading
import time

import websocket  # websocket-client

from .. import log
from ..models import Candle, DataQualityError, Quote, now_ms, validate_candle


class LiveFeed:
    def __init__(self, cfg, db, on_candle=None):
        self.cfg = cfg
        self.db = db
        self.on_candle = on_candle  # called as on_candle(interval_minutes, Candle) for new closed candles
        self.symbol = cfg.symbol
        self.entry = cfg.data.entry_interval
        self.trend = cfg.data.trend_interval
        self.quote: Quote | None = None
        self.last_candle_ms = 0  # local time we last saw any kline message
        self.connected = False
        self.reconnects = 0
        self.duplicates = 0
        self.out_of_order = 0
        self._last_seen: dict[int, int] = {}
        self._ws = None
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

    # ---------- public API ----------
    def start(self):
        self._thread = threading.Thread(target=self._run_forever, daemon=True, name="live-feed")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._ws:
            self._ws.close()

    def get_quote(self) -> Quote | None:
        with self._lock:
            return self.quote

    def quote_age_seconds(self) -> float:
        q = self.get_quote()
        return float("inf") if q is None else (now_ms() - q.ts_ms) / 1000

    def is_stale(self) -> bool:
        return not self.connected or self.quote_age_seconds() > self.cfg.data.quote_stale_seconds

    # ---------- connection loop ----------
    def _run_forever(self):
        delay = self.cfg.data.reconnect_base_seconds
        while not self._stop.is_set():
            started = time.time()
            self._ws = websocket.WebSocketApp(
                self.cfg.data.ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=lambda ws, e: log.error(f"Live feed error: {e}"),
                on_close=self._on_close,
            )
            self._ws.run_forever(ping_interval=None)  # we send Bybit's own {"op":"ping"} below
            self.connected = False
            if self._stop.is_set():
                break
            self.reconnects += 1
            if time.time() - started > 60:  # it ran fine for a while: reset the wait
                delay = self.cfg.data.reconnect_base_seconds
            wait = delay + random.uniform(0, delay * 0.3)  # small random jitter
            log.warn(f"Live feed lost; reconnecting in {wait:.1f}s (attempt {self.reconnects})")
            self._stop.wait(wait)
            delay = min(delay * 2, self.cfg.data.reconnect_max_seconds)

    def _on_open(self, ws):
        self.connected = True
        topics = [f"kline.{self.entry}.{self.symbol}", f"kline.{self.trend}.{self.symbol}",
                  f"orderbook.1.{self.symbol}"]
        ws.send(json.dumps({"op": "subscribe", "args": topics}))
        log.ok(f"Live feed connected ({self.symbol})")
        threading.Thread(target=self._ping_loop, args=(ws,), daemon=True).start()

    def _on_close(self, ws, code, msg):
        self.connected = False
        if not self._stop.is_set():
            log.warn(f"Live feed closed (code {code})")

    def _ping_loop(self, ws):
        while not self._stop.is_set() and ws is self._ws and self.connected:
            self._stop.wait(self.cfg.data.ws_ping_seconds)
            try:
                if self.connected and ws is self._ws:
                    ws.send(json.dumps({"op": "ping"}))
            except Exception:
                return

    # ---------- message handling ----------
    def _on_message(self, ws, raw):
        try:
            msg = json.loads(raw)
            topic = msg.get("topic", "")
            if topic.startswith("orderbook."):
                self._handle_book(msg)
            elif topic.startswith("kline."):
                self._handle_kline(msg)
            elif msg.get("success") is False:
                log.error(f"Live feed request rejected: {msg}")
        except Exception as e:  # never let one bad message kill the feed
            log.error(f"Bad live-feed message ignored: {e}")

    def _handle_book(self, msg):
        d = msg["data"]
        if not d.get("b") or not d.get("a"):
            return  # one side empty: skip rather than guess
        bid, ask = float(d["b"][0][0]), float(d["a"][0][0])
        if bid <= 0 or ask < bid:
            log.error(f"Rejected bad quote {bid}/{ask}")
            return
        with self._lock:
            self.quote = Quote(bid, ask, now_ms())

    def _handle_kline(self, msg):
        interval = int(msg["topic"].split(".")[1])
        self.last_candle_ms = now_ms()
        for k in msg["data"]:
            if not k.get("confirm"):
                continue  # still forming: ignore until it closes
            c = Candle(int(k["start"]), float(k["open"]), float(k["high"]), float(k["low"]),
                       float(k["close"]), float(k["volume"]))
            try:
                validate_candle(c)
            except DataQualityError as e:
                log.error(f"Bad candle dropped: {e}")
                continue
            last = self._last_seen.get(interval)
            if last is not None and c.start < last:
                self.out_of_order += 1
                log.warn(f"Out-of-order {interval}m candle ignored")
                continue
            if self.db.save_candle(self.symbol, interval, c):
                self._last_seen[interval] = c.start
                if self.on_candle:
                    self.on_candle(interval, c)
            else:
                self.duplicates += 1
