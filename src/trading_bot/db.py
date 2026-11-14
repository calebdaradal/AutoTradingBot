"""SQLite storage. One file holds candles, decisions, orders, fills, equity and events.

Decisions, orders, fills, equity and events are IMMUTABLE: the database itself refuses
to change or delete them (triggers below), so the history can always be trusted.
"""
import json
import sqlite3
from pathlib import Path

from .models import Candle, interval_ms, now_ms

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles(
  symbol TEXT NOT NULL, interval INTEGER NOT NULL, start_ms INTEGER NOT NULL,
  open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL,
  PRIMARY KEY(symbol, interval, start_ms)
);
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts_ms INTEGER NOT NULL, candle_start_ms INTEGER,
  kind TEXT NOT NULL, action TEXT NOT NULL, reasons TEXT NOT NULL, details TEXT, strategy_version TEXT
);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, client_order_id TEXT NOT NULL UNIQUE, ts_ms INTEGER NOT NULL,
  side TEXT NOT NULL, order_type TEXT NOT NULL, qty TEXT NOT NULL, ref_price TEXT NOT NULL,
  status TEXT NOT NULL, reject_reason TEXT, decision_id INTEGER
);
CREATE TABLE IF NOT EXISTS fills(
  id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
  ts_ms INTEGER NOT NULL, side TEXT NOT NULL, qty TEXT NOT NULL, price TEXT NOT NULL, fee TEXT NOT NULL,
  cash_after TEXT NOT NULL, base_after TEXT NOT NULL,
  realized_gross TEXT NOT NULL, realized_net TEXT NOT NULL, reason TEXT
);
CREATE TABLE IF NOT EXISTS equity(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts_ms INTEGER NOT NULL, cash TEXT NOT NULL, base_qty TEXT NOT NULL,
  mark_price TEXT NOT NULL, equity TEXT NOT NULL, peak_equity TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts_ms INTEGER NOT NULL, level TEXT NOT NULL,
  kind TEXT NOT NULL, message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, started_ms INTEGER NOT NULL, profile TEXT NOT NULL,
  strategy_version TEXT NOT NULL, config_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

IMMUTABLE = ("decisions", "orders", "fills", "equity", "events")


class Database:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=30, isolation_level=None,
                                    check_same_thread=False)  # we manage transactions; one connection per thread
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        for t in IMMUTABLE:
            for op in ("UPDATE", "DELETE"):
                self.conn.execute(
                    f"CREATE TRIGGER IF NOT EXISTS {t}_no_{op.lower()} BEFORE {op} ON {t} "
                    f"BEGIN SELECT RAISE(ABORT, '{t} is an immutable journal'); END"
                )

    def close(self):
        self.conn.close()

    # ---- transactions: everything inside succeeds together or not at all ----
    def begin(self):
        self.conn.execute("BEGIN IMMEDIATE")

    def commit(self):
        self.conn.execute("COMMIT")

    def rollback(self):
        if self.conn.in_transaction:
            self.conn.execute("ROLLBACK")

    # ---- candles (only CLOSED candles are ever stored) ----
    def save_candle(self, symbol: str, interval: int, c: Candle) -> bool:
        """Returns True if new, False if we already had it (duplicate ignored)."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO candles VALUES(?,?,?,?,?,?,?,?)",
            (symbol, interval, c.start, c.open, c.high, c.low, c.close, c.volume),
        )
        return cur.rowcount == 1

    def save_candles(self, symbol: str, interval: int, candles) -> int:
        self.begin()
        try:
            n = sum(self.save_candle(symbol, interval, c) for c in candles)
            self.commit()
            return n
        except Exception:
            self.rollback()
            raise

    def load_candles(self, symbol, interval, start_ms=None, end_ms=None, limit=None):
        q = "SELECT start_ms,open,high,low,close,volume FROM candles WHERE symbol=? AND interval=?"
        args = [symbol, interval]
        if start_ms is not None:
            q += " AND start_ms>=?"
            args.append(start_ms)
        if end_ms is not None:
            q += " AND start_ms<=?"
            args.append(end_ms)
        if limit:  # latest N, returned in time order
            q = f"SELECT * FROM ({q} ORDER BY start_ms DESC LIMIT {int(limit)}) ORDER BY start_ms"
        else:
            q += " ORDER BY start_ms"
        return [Candle(*tuple(r)) for r in self.conn.execute(q, args)]

    def candle_bounds(self, symbol, interval):
        r = self.conn.execute(
            "SELECT MIN(start_ms) a, MAX(start_ms) b, COUNT(*) n FROM candles WHERE symbol=? AND interval=?",
            (symbol, interval),
        ).fetchone()
        return r["a"], r["b"], r["n"]

    def find_gaps(self, symbol, interval, from_ms=None, to_ms=None):
        """Return the start times of candles that should exist but are missing."""
        a, b, _ = self.candle_bounds(symbol, interval)
        if a is None:
            return []
        lo = max(a, from_ms) if from_ms else a
        hi = min(b, to_ms) if to_ms else b
        step = interval_ms(interval)
        have = {
            r[0]
            for r in self.conn.execute(
                "SELECT start_ms FROM candles WHERE symbol=? AND interval=? AND start_ms BETWEEN ? AND ?",
                (symbol, interval, lo, hi),
            )
        }
        first = lo + (-lo) % step
        return [t for t in range(first, hi + 1, step) if t not in have]

    # ---- journals ----
    def log_event(self, level: str, kind: str, message: str):
        self.conn.execute(
            "INSERT INTO events(ts_ms,level,kind,message) VALUES(?,?,?,?)",
            (now_ms(), level, kind, message),
        )

    def log_decision(self, candle_start_ms, kind, action, reasons, details=None, strategy_version=None) -> int:
        cur = self.conn.execute(
            "INSERT INTO decisions(ts_ms,candle_start_ms,kind,action,reasons,details,strategy_version) "
            "VALUES(?,?,?,?,?,?,?)",
            (now_ms(), candle_start_ms, kind, action, "; ".join(reasons),
             json.dumps(details, default=str) if details else None, strategy_version),
        )
        return cur.lastrowid

    # ---- small key/value state (position, kill switch, etc.) ----
    def set_state(self, key: str, value):
        self.conn.execute(
            "INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )

    def get_state(self, key: str, default=None):
        r = self.conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default
