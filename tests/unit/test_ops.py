"""Track A: the paper-run health report reads the journals correctly."""
import json
from types import SimpleNamespace

from trading_bot.ops import FeedWatcher, ops_flags, ops_report, print_ops

DAY = 86_400_000
STEP = 15 * 60_000


def _feed(**kw):
    return SimpleNamespace(**{"reconnects": 0, "duplicates": 0, "out_of_order": 0, **kw})


def _run(db, started_ms, version="trend_momentum-1.0"):
    db.conn.execute("INSERT INTO runs(started_ms,profile,strategy_version,config_json) VALUES(?,?,?,?)",
                    (started_ms, "local_sim", version, "{}"))


def _fill(db, side, ref, px, status="FILLED", cid="a"):
    cur = db.conn.execute(
        "INSERT INTO orders(client_order_id,ts_ms,side,order_type,qty,ref_price,status) VALUES(?,?,?,?,?,?,?)",
        (cid, 1, side, "MARKET", "1", str(ref), status))
    if status == "FILLED":
        db.conn.execute(
            "INSERT INTO fills(order_id,ts_ms,side,qty,price,fee,cash_after,base_after,realized_gross,realized_net) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)", (cur.lastrowid, 1, side, "1", str(px), "0", "0", "0", "0", "0"))


def test_watcher_logs_only_when_counters_grow(db):
    w = FeedWatcher(db)
    w.check(_feed(reconnects=2), stale=False)
    w.check(_feed(reconnects=2), stale=False)          # no change: no new event
    w.check(_feed(reconnects=3), stale=False)
    rows = db.conn.execute("SELECT message FROM events WHERE kind='feed_reconnects'").fetchall()
    assert [json.loads(r["message"])["new"] for r in rows] == [2, 1]


def test_watcher_measures_how_long_the_feed_was_stale(db):
    w = FeedWatcher(db)
    w.check(_feed(), stale=True, ts_ms=1_000)
    w.check(_feed(), stale=True, ts_ms=5_000)          # still the same episode
    w.check(_feed(), stale=False, ts_ms=11_000)
    rows = db.conn.execute("SELECT message FROM events WHERE kind='stale_end'").fetchall()
    assert len(rows) == 1 and json.loads(rows[0]["message"])["seconds"] == 10.0


def test_empty_journal_gives_a_clean_zero_report(db, cfg):
    r = ops_report(db, cfg, now=1_000)
    assert r["days_running"] == 0 and r["closed_trades"] == 0 and r["avg_slip_bps"] is None
    assert ops_flags(r) == []


def test_days_restarts_and_missed_candles(db, cfg):
    _run(db, 0)
    _run(db, DAY)                                      # one restart
    for i in range(10):                                # saw only 10 of the 96 candles in the first day
        db.log_decision(i * STEP, "signal", "HOLD", ["x"])
    r = ops_report(db, cfg, now=DAY)
    assert r["days_running"] == 1 and r["restarts"] == 1
    assert r["expected_candles"] == 96 and r["seen_candles"] == 10 and r["missed_candles"] == 86
    assert any("missed 86 candles" in f for f in ops_flags(r))


def test_slippage_sign_means_paying_more_than_the_middle_price(db, cfg):
    _fill(db, "BUY", 100.0, 100.10, cid="b")           # paid 10 bps more
    _fill(db, "SELL", 100.0, 99.90, cid="s")           # received 10 bps less
    r = ops_report(db, cfg, now=1)
    assert r["fills"] == 2
    assert abs(r["avg_slip_bps"] - 10.0) < 0.01 and abs(r["worst_slip_bps"] - 10.0) < 0.01
    assert r["closed_trades"] == 1


def test_rejected_orders_are_counted_with_reasons(db, cfg):
    _fill(db, "BUY", 100.0, 100.0, cid="ok")
    db.conn.execute("INSERT INTO orders(client_order_id,ts_ms,side,order_type,qty,ref_price,status,reject_reason) "
                    "VALUES('r',1,'BUY','MARKET','1','100','REJECTED','too small')")
    r = ops_report(db, cfg, now=1)
    assert r["orders"] == {"FILLED": 1, "REJECTED": 1}
    assert r["reject_reasons"][0]["reject_reason"] == "too small"


def test_expensive_fills_and_errors_are_flagged(db, cfg):
    _fill(db, "BUY", 100.0, 101.0, cid="b")            # 100 bps, far above the modeled cost
    db.log_event("ERROR", "boom", "something broke")
    db.log_event("ERROR", "reconcile", "{}")
    r = ops_report(db, cfg, now=1)
    assert r["run_errors"] == 1 and r["reconcile_failures"] == 1   # reconcile is not double counted
    text = " ".join(ops_flags(r))
    assert "bps" in text and "error" in text and "did not match" in text


def test_changed_settings_make_the_clock_unclean(db, cfg):
    _run(db, 0, "trend_momentum-1.0")
    _run(db, 1, "trend_momentum-1.1")
    assert any("not clean" in f for f in ops_flags(ops_report(db, cfg, now=2)))


def test_print_ops_says_not_yet_before_the_gate(db, cfg):
    _run(db, 0)
    lines = []
    print_ops(ops_report(db, cfg, now=DAY), lines.append)
    assert any("NOT YET" in line for line in lines)
