"""Track A: operational health of the paper run.

Answers "is the simulator itself behaving?" (separate from "is the strategy any good?").
The runner writes small events into the journal; `ops_report` reads them back over the whole run.
"""
import json

from .models import interval_ms, now_ms

GATE_DAYS, GATE_TRADES = 30, 30


class FeedWatcher:
    """Turns the live feed's running counters into journal events (one event per change)."""

    def __init__(self, db):
        self.db = db
        self._seen = {"reconnects": 0, "duplicates": 0, "out_of_order": 0}
        self._stale_since: int | None = None

    def check(self, feed, stale: bool, ts_ms: int | None = None):
        ts = ts_ms if ts_ms is not None else now_ms()
        for name, level in (("reconnects", "WARN"), ("duplicates", "INFO"), ("out_of_order", "WARN")):
            cur = getattr(feed, name, 0)
            if cur > self._seen[name]:
                self.db.log_event(level, f"feed_{name}", json.dumps({"new": cur - self._seen[name], "total": cur}))
                self._seen[name] = cur
        if stale and self._stale_since is None:
            self._stale_since = ts
        elif not stale and self._stale_since is not None:
            secs = (ts - self._stale_since) / 1000
            self.db.log_event("WARN", "stale_end", json.dumps({"seconds": round(secs, 1)}))
            self._stale_since = None


def ops_report(db, cfg, now: int | None = None) -> dict:
    c = db.conn
    now = now if now is not None else now_ms()
    runs = [dict(r) for r in c.execute("SELECT id, started_ms, strategy_version FROM runs ORDER BY id")]
    first = runs[0]["started_ms"] if runs else None
    days = (now - first) / 86_400_000 if first is not None else 0.0

    def n_events(kind: str) -> int:
        return c.execute("SELECT COUNT(*) n FROM events WHERE kind=?", (kind,)).fetchone()["n"]

    def sum_new(kind: str) -> int:
        tot = 0
        for r in c.execute("SELECT message FROM events WHERE kind=?", (kind,)):
            try:
                tot += int(json.loads(r["message"]).get("new", 0))
            except (ValueError, TypeError):
                pass
        return tot

    stale_secs = []
    for r in c.execute("SELECT message FROM events WHERE kind='stale_end'"):
        try:
            stale_secs.append(float(json.loads(r["message"])["seconds"]))
        except (ValueError, KeyError, TypeError):
            pass

    # Did the bot see every 15-minute candle since it first started? Missing ones = it was off or blind.
    step = interval_ms(cfg.data.entry_interval)
    expected = int((now - first) // step) if first is not None else 0
    seen = c.execute("SELECT COUNT(DISTINCT candle_start_ms) n FROM decisions WHERE kind='signal'").fetchone()["n"]
    missed = max(0, expected - seen)

    orders = {r["status"]: r["n"] for r in c.execute("SELECT status, COUNT(*) n FROM orders GROUP BY status")}
    rejects = [dict(r) for r in c.execute(
        "SELECT reject_reason, COUNT(*) n FROM orders WHERE status='REJECTED' GROUP BY reject_reason ORDER BY n DESC LIMIT 3")]

    # Execution: how far from the quoted middle price did each simulated fill land? (basis points: 1 bp = 0.01%)
    slips = []
    for r in c.execute("SELECT o.side, o.ref_price, f.price FROM orders o JOIN fills f ON f.order_id=o.id"):
        ref, px = float(r["ref_price"]), float(r["price"])
        if ref > 0:
            slips.append((px / ref - 1) * 1e4 * (1 if r["side"] == "BUY" else -1))  # positive = paid more than mid
    modeled = (cfg.costs.half_spread + cfg.costs.slippage) * 1e4

    closed = c.execute("SELECT COUNT(*) n FROM fills WHERE side='SELL'").fetchone()["n"]
    fz = db.get_state("frozen_config")
    return {
        "days_running": days, "restarts": max(0, len(runs) - 1), "closed_trades": closed,
        "frozen_id": fz.get("hash") if isinstance(fz, dict) else None,
        "refreezes": max(0, len(db.get_state("config_freeze_history", [])) - 1),
        "strategy_versions": sorted({r["strategy_version"] for r in runs}),
        "expected_candles": expected, "seen_candles": seen, "missed_candles": missed,
        "feed_reconnects": sum_new("feed_reconnects"), "duplicates": sum_new("feed_duplicates"),
        "out_of_order": sum_new("feed_out_of_order"),
        "stale_episodes": len(stale_secs), "stale_seconds": sum(stale_secs),
        "gap_repairs": n_events("gap_repair"), "run_errors": c.execute(
            "SELECT COUNT(*) n FROM events WHERE level='ERROR' AND kind!='reconcile'").fetchone()["n"],
        "reconcile_failures": n_events("reconcile"),
        "orders": orders, "reject_reasons": rejects, "duplicate_orders": n_events("order_duplicate"),
        "fills": len(slips), "avg_slip_bps": sum(slips) / len(slips) if slips else None,
        "worst_slip_bps": max(slips) if slips else None, "modeled_slip_bps": modeled,
    }


def ops_flags(r: dict) -> list[str]:
    """Plain-language list of things that need a human look. Empty list = nothing odd."""
    out = []
    if r["restarts"] > 0 and r["missed_candles"] > 0:
        out.append(f"The bot missed {r['missed_candles']} candles (it was off or blind). Gaps weaken the test.")
    if r["reconcile_failures"]:
        out.append(f"{r['reconcile_failures']} restart check(s) found balances that did not match the journal.")
    if r["out_of_order"]:
        out.append(f"{r['out_of_order']} out-of-order candle(s) were ignored.")
    if r["avg_slip_bps"] is not None and r["avg_slip_bps"] > 3 * r["modeled_slip_bps"]:
        out.append(f"Fills are costing {r['avg_slip_bps']:.1f} bps on average vs {r['modeled_slip_bps']:.1f} assumed.")
    if r["run_errors"]:
        out.append(f"{r['run_errors']} error(s) in the journal. Check the events table.")
    if len(r["strategy_versions"]) > 1 or r["refreezes"]:
        out.append("The settings or strategy version changed during the run. The 30-day clock is not clean.")
    return out


def print_ops(r: dict, say):
    say(f"Paper run: {r['days_running']:.1f} of {GATE_DAYS} days | {r['closed_trades']} of {GATE_TRADES} closed trades | "
        f"{r['restarts']} restart(s)")
    say(f"Frozen settings id: {r['frozen_id'] or 'not frozen yet'}")
    say(f"Candles seen: {r['seen_candles']} of {r['expected_candles']} expected (missed {r['missed_candles']})")
    say(f"Live feed: {r['feed_reconnects']} reconnects | {r['stale_episodes']} stale periods "
        f"({r['stale_seconds']:.0f}s total) | {r['duplicates']} duplicates | {r['out_of_order']} out of order | "
        f"{r['gap_repairs']} gap repairs")
    o = r["orders"]
    say(f"Orders: {o.get('FILLED', 0)} filled | {o.get('REJECTED', 0)} rejected | {r['duplicate_orders']} duplicate blocked")
    for x in r["reject_reasons"]:
        say(f"  rejected because: {x['reject_reason']} ({x['n']}x)")
    if r["avg_slip_bps"] is not None:
        say(f"Fill cost vs middle price: avg {r['avg_slip_bps']:.1f} bps, worst {r['worst_slip_bps']:.1f} bps "
            f"(model assumes {r['modeled_slip_bps']:.1f}). 1 bps = 0.01%.")
    flags = ops_flags(r)
    say("Needs a look: " + " | ".join(flags) if flags else "Needs a look: nothing odd so far.")
    if r["days_running"] < GATE_DAYS or r["closed_trades"] < GATE_TRADES:
        say(f"Gate: NOT YET. Needs {GATE_DAYS} days and {GATE_TRADES} trades.")
    else:
        say("Gate: time and trade count reached. Review results before any next step.")
