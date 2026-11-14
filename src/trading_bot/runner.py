"""The paper-trading loop. Watches live BTC/USDT prices and trades with FAKE money.

Every 15 minutes (when a candle closes):  update data -> compute indicators -> ask the strategy ->
ask the risk manager -> (maybe) place a simulated order -> save everything.
Between candles: watch the live price so a stop-loss or target is caught quickly.
"""
import queue
import signal
import time
from dataclasses import asdict

from . import log
from .config import starting_balance_usdt
from .data.bybit import BybitError, BybitPublic
from .data.sync import repair_gaps, sync_history
from .data.ws_feed import LiveFeed
from .db import Database
from .execution import PaperBroker, load_portfolio, reconcile
from .features import build_features
from .models import interval_ms, now_ms
from .ops import FeedWatcher
from .portfolio import Portfolio
from .research import check_config_freeze, config_hash
from .risk import RiskManager, utc_day
from .strategies import BUY, SELL, Context, Position, TrendMomentum


class Runner:
    def __init__(self, cfg, heartbeat_seconds: int = 60):
        self.cfg = cfg
        self.sym = cfg.symbol
        self.entry_iv, self.trend_iv = cfg.data.entry_interval, cfg.data.trend_interval
        self.heartbeat = heartbeat_seconds
        self.db = Database(cfg.data.db_path)
        self.client = BybitPublic(cfg.data.rest_url, cfg.category, cfg.symbol)
        self.strat = TrendMomentum(cfg.strategy)
        self.pf = Portfolio(starting_balance_usdt(cfg), cfg.costs, cfg.exchange_rules)
        self.risk = RiskManager(cfg.risk, cfg.exchange_rules)
        self.broker = PaperBroker(cfg, self.db, self.pf)
        self.pos: Position | None = None
        self.q: queue.Queue = queue.Queue()
        self.feed: LiveFeed | None = None
        self.kill_handled = False
        self.was_stale = False
        self.watcher = FeedWatcher(self.db)
        self.last_mark = None
        self._stop = False

    # ------------------------------------------------------------------ startup
    def start(self):
        cfg, db = self.cfg, self.db
        state = check_config_freeze(db, cfg)   # refuses to start if settings changed since first start
        log.ok(f"Settings frozen (id {config_hash(cfg)})" if state == "frozen"
               else f"Settings match the frozen paper config (id {config_hash(cfg)})")
        db.conn.execute("INSERT INTO runs(started_ms,profile,strategy_version,config_json) VALUES(?,?,?,?)",
                        (now_ms(), cfg.profile, self.strat.version, str(cfg.raw)))
        db.log_event("INFO", "run_start", f"strategy {self.strat.version}, settings {config_hash(cfg)}")
        log.ok(f"Starting paper trading: {self.sym}, profile '{cfg.profile}', strategy {self.strat.version}")
        log.note("Paper trading = pretend money, real prices. No real orders are ever sent.")
        self._restore_state()
        self._load_data()
        self.feed = LiveFeed(cfg, Database(cfg.data.db_path), on_candle=lambda iv, c: self.q.put((iv, c)))
        self.feed.start()

    def _restore_state(self):
        db = self.db
        saved = db.get_state("portfolio")
        if saved:
            load_portfolio(self.pf, saved)
            log.ok(f"Restored saved account: {self.pf.cash:.2f} USDT cash, {self.pf.base:.6f} BTC")
        else:
            log.ok(f"New account: {self.pf.cash:.2f} USDT (about PHP {self.cfg.account.starting_balance_php:.0f})")
        reconcile(db, self.pf)
        p = db.get_state("position")
        self.pos = Position(**p) if p else None
        if self.pos and self.pf.base < 1e-9:
            log.error("Saved position does not match balances; clearing it")
            self.pos = None
        if self.pos is None and self.pf.base > 1e-9:
            log.error("Holding BTC without a saved position record - please review the journal")
        self.risk.load(db.get_state("risk"))
        if self.pos:
            log.ok(f"Resumed open position: {self.pos.qty:.6f} BTC, stop {self.pos.stop:,.1f}, target {self.pos.target:,.1f}")

    def _load_data(self):
        for iv, days in ((self.entry_iv, 6), (self.trend_iv, 18)):
            try:
                sync_history(self.client, self.db, self.sym, iv, days)
                repair_gaps(self.client, self.db, self.sym, iv)
            except BybitError as e:
                log.error(f"Could not update {iv}m data: {e}")

    # ------------------------------------------------------------------ main loop
    def run(self, minutes: float | None = None):
        self._listen_for_docker_stop()
        self.start()
        deadline = time.time() + minutes * 60 if minutes else None
        next_beat = time.time() + 10
        try:
            while not self._stop and (deadline is None or time.time() < deadline):
                try:
                    iv, candle = self.q.get(timeout=1)
                    if iv == self.entry_iv:
                        self.on_entry_close(candle)
                except queue.Empty:
                    pass
                self._poll_controls()
                self._watch_price()
                if time.time() >= next_beat:
                    self._heartbeat()
                    next_beat = time.time() + self.heartbeat
        except KeyboardInterrupt:
            log.note("Stop requested (Ctrl+C)")
        finally:
            self.shutdown()

    def _listen_for_docker_stop(self):
        """Docker stops a container with SIGTERM (a 'please stop' signal). Treat it like Ctrl+C: save, then exit."""
        def on_stop(signum, frame):
            log.note("Stop requested (Docker/system shutdown)")
            self._stop = True
        try:
            signal.signal(signal.SIGTERM, on_stop)
        except ValueError:   # not the main thread (e.g. in tests); skip
            pass

    def shutdown(self):
        if self.feed:
            self.feed.stop()
        self._save_state()
        self.db.log_event("INFO", "run_stop", "stopped safely")
        log.ok("Stopped safely. Account and position are saved; restart any time to continue.")
        self.db.close()

    # ------------------------------------------------------------------ helpers
    def _save_state(self):
        from .execution import portfolio_state
        self.db.set_state("portfolio", portfolio_state(self.pf))
        self.db.set_state("position", asdict(self.pos) if self.pos else None)
        self.db.set_state("risk", self.risk.to_dict())

    def _fresh_quote(self):
        q = self.feed.get_quote() if self.feed else None
        if q and not self.feed.is_stale():
            return q
        try:
            return self.client.fetch_quote()
        except Exception as e:
            log.error(f"No fresh price available: {e}")
            return None

    def _mark(self):
        q = self.feed.get_quote() if self.feed else None
        return q.mid if q else self.last_mark

    def _poll_controls(self):
        db = self.db
        kill = bool(db.get_state("kill_switch", False))
        if kill and not self.kill_handled:
            self.kill_handled = True
            log.warn("EMERGENCY STOP is ON: no new buys; closing any open position")
            db.log_event("WARN", "kill_switch", "emergency stop activated")
            if self.pos:
                self._exit("emergency stop", "kill")
        elif not kill and self.kill_handled:
            self.kill_handled = False
            log.ok("Emergency stop cleared")
        if db.get_state("clear_halt", False):
            self.risk.halted = None
            self.pf.peak_equity = self.pf.equity(self._mark() or 0) if self._mark() else self.pf.peak_equity
            db.set_state("clear_halt", False)
            self._save_state()
            log.ok("Drawdown halt cleared by operator")
        stale = self.feed.is_stale() if self.feed else False
        if stale and not self.was_stale:
            log.warn("Market data is STALE: new buys are blocked until it recovers")
            db.log_event("WARN", "stale_data", "feed stale")
        if not stale and self.was_stale:
            log.ok("Market data is fresh again")
        self.was_stale = stale
        if self.feed:
            self.watcher.check(self.feed, stale)

    def _watch_price(self):
        """Between candles: exit quickly if the live price crosses stop or target."""
        if not self.pos or not self.feed or self.feed.is_stale():
            return
        q = self.feed.get_quote()
        if q.bid <= self.pos.stop:
            self._exit("stop-loss (live price)", "stop", q)
        elif q.bid >= self.pos.target:
            self._exit("target reached (live price)", "target", q)

    def _heartbeat(self):
        q = self.feed.get_quote()
        if not q:
            log.warn("Waiting for the first live price...")
            return
        self.last_mark = q.mid
        eq = self.pf.equity(q.mid)
        where = f"holding {self.pf.base:.6f} BTC" if self.pos else "no position"
        stale = " | DATA STALE" if self.feed.is_stale() else ""
        log.ok(f"BTC {q.mid:,.1f} | equity {eq:.3f} USDT ({eq / self.cfg_start() - 1:+.2%}) | {where}{stale}")

    def cfg_start(self):
        return starting_balance_usdt(self.cfg)

    # ------------------------------------------------------------------ candle close
    def on_entry_close(self, candle):
        cfg, db = self.cfg, self.db
        gaps = db.find_gaps(self.sym, self.entry_iv, candle.start - 200 * interval_ms(self.entry_iv))
        if gaps:
            db.log_event("WARN", "gap_repair", f"{len(gaps)} missing {self.entry_iv}m candle(s)")
            repair_gaps(self.client, db, self.sym, self.entry_iv)
        entry = db.load_candles(self.sym, self.entry_iv, limit=cfg.data.warmup_candles)
        trend = db.load_candles(self.sym, self.trend_iv, limit=cfg.data.warmup_candles)
        feats = build_features(entry, trend, cfg.strategy, self.entry_iv, self.trend_iv)
        f = feats[-1]
        if f.start != candle.start:
            log.warn("Latest stored candle differs from the one just closed; skipping this round")
            return
        self.last_mark = candle.close
        if self.pos:
            self.pos.bars_held += 1
        ctx = self._context(candle.start)
        d = self.strat.evaluate(f, self.pos, ctx)
        did = db.log_decision(candle.start, "signal", d.action, d.reasons, d.details, self.strat.version)
        log.note(f"15m candle closed @ {candle.close:,.1f} -> {d.action}: {'; '.join(d.reasons)}")

        if d.action == BUY:
            self._enter(f, candle, did)
        elif d.action == SELL and self.pos:
            self._exit(d.reasons[0], "sig")
        self._record_equity()
        self._save_state()

    def _context(self, ts_ms: int) -> Context:
        today = utc_day(ts_ms)
        rows = self.db.conn.execute(
            "SELECT ts_ms FROM fills WHERE side='BUY'").fetchall()
        trades_today = sum(1 for r in rows if utc_day(r["ts_ms"]) == today)
        last_exit = self.db.get_state("last_exit_ms")
        since = (ts_ms - last_exit) // interval_ms(self.entry_iv) if last_exit else 10_000
        return Context(trades_today, since)

    def _record_equity(self):
        mark = self._mark()
        if mark is None:
            return
        eq = self.pf.equity(mark)
        self.pf.update_peak(mark)
        self.db.conn.execute(
            "INSERT INTO equity(ts_ms,cash,base_qty,mark_price,equity,peak_equity) VALUES(?,?,?,?,?,?)",
            (now_ms(), str(self.pf.cash), str(self.pf.base), str(mark), str(eq), str(self.pf.peak_equity)))

    def _enter(self, f, candle, decision_id):
        cfg, db = self.cfg, self.db
        q = self._fresh_quote()
        mid = q.mid if q else candle.close
        eq = self.pf.equity(mid)
        ok, why = self.risk.check_entry(
            self.sym, eq, self.pf.peak_equity, now_ms(), quote=q,
            data_stale=(q is None),
            trading_enabled=cfg.trading_enabled, kill_switch=bool(db.get_state("kill_switch", False)))
        if not ok:
            db.log_decision(candle.start, "blocked", "HOLD", why, None, self.strat.version)
            log.warn(f"Buy blocked by risk rules: {'; '.join(why)}")
            return
        stop = mid - cfg.strategy.stop_atr_mult * f.atr
        qty = self.risk.size(eq, self.pf.cash, mid, stop, cfg.costs.taker_fee)

        def after(fill):
            self.pos = self.strat.make_position(fill.price, fill.qty, f.atr, candle.start)
            self.risk.record_order()
            return {"position": asdict(self.pos), "risk": self.risk.to_dict()}

        res = self.broker.submit(f"BUY-{self.sym}-{candle.start}", "BUY", qty, mid, q,
                                 reason="strategy entry", decision_id=decision_id, extra_state=after)
        self._note_duplicate(res)

    def _note_duplicate(self, res):
        if res.status == "DUPLICATE":
            self.db.log_event("WARN", "order_duplicate", "an order with the same id was blocked")

    def _exit(self, reason: str, code: str, quote=None):
        if not self.pos:
            return
        q = quote or self._fresh_quote()
        mid = q.mid if q else (self.last_mark or self.pos.entry_price)
        pos = self.pos

        def after(fill):
            self.risk.record_trade_result(fill.realized_net, now_ms())
            self.risk.record_order()
            self.pos = None
            return {"position": None, "risk": self.risk.to_dict(), "last_exit_ms": now_ms()}

        res = self.broker.submit(f"SELL-{self.sym}-{pos.entry_start}-{code}", "SELL", pos.qty, mid, q,
                                 reason=reason, extra_state=after)
        self._note_duplicate(res)
        if res.status == "FILLED":
            f = res.fill
            log.ok(f"Trade closed: profit before costs {f.realized_gross:+.4f}, after costs {f.realized_net:+.4f} USDT")
