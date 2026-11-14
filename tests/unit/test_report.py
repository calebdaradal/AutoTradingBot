"""Paper report: the extra performance numbers and the paper round-trip builder (feeds diagnose-paper)."""
import json

from trading_bot.diagnose import diagnose_trades
from trading_bot.report import paper_report, paper_trades

STEP = 15 * 60_000


def _fill(db, ts, side, px, net=0.0, gross=0.0, reason=None, cid=None):
    cur = db.conn.execute(
        "INSERT INTO orders(client_order_id,ts_ms,side,order_type,qty,ref_price,status) VALUES(?,?,?,?,?,?,?)",
        (cid or f"o{ts}{side}", ts, side, "MARKET", "1", str(px), "FILLED"))
    db.conn.execute(
        "INSERT INTO fills(order_id,ts_ms,side,qty,price,fee,cash_after,base_after,realized_gross,realized_net,reason) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)", (cur.lastrowid, ts, side, "1", str(px), "0", "0", "0", str(gross), str(net), reason))


def _trade(db, t, net):
    _fill(db, t, "BUY", 100.0)
    _fill(db, t + STEP, "SELL", 100.0, net=net, gross=net, reason="stop-loss" if net < 0 else "target reached")


def test_no_trades_gives_empty_extras(db):
    r = paper_report(db, 100.0)
    assert r["profit_factor"] is None and r["avg_trade"] is None and r["max_losing_streak"] == 0


def test_profit_factor_averages_and_losing_streak(db):
    for i, net in enumerate([3.0, -1.0, -1.0, -2.0, 2.0, -1.0]):
        _trade(db, (i + 1) * 10 * STEP, net)
    r = paper_report(db, 100.0)
    assert abs(r["profit_factor"] - 5.0 / 5.0) < 1e-9          # won 5, lost 5
    assert abs(r["avg_trade"] - 0.0) < 1e-9
    assert abs(r["avg_win"] - 2.5) < 1e-9 and abs(r["avg_loss"] - (-1.25)) < 1e-9
    assert r["max_losing_streak"] == 3


def test_profit_factor_is_none_with_no_losers(db):
    _trade(db, STEP, 2.0)
    assert paper_report(db, 100.0)["profit_factor"] is None


def test_paper_trades_measure_best_and_worst_price_from_candles(db):
    sym, iv = "BTCUSDT", 15
    t0 = 100 * STEP
    for i, (hi, lo) in enumerate([(104.0, 99.0), (101.0, 95.0), (100.0, 97.0)]):
        db.conn.execute("INSERT INTO candles VALUES(?,?,?,?,?,?,?,?)", (sym, iv, t0 + i * STEP, 100, hi, lo, 100, 1))
    db.log_decision(t0 - STEP, "signal", "BUY", ["all entry conditions met"],
                    {"close": 100.0, "rsi": 55.0, "atr": 1.0, "trend_fast": 101.0, "trend_slow": 100.0,
                     "volume": 20.0, "vol_ma": 10.0})
    _fill(db, t0, "BUY", 100.0)
    _fill(db, t0 + 2 * STEP, "SELL", 97.0, net=-3.0, gross=-3.0, reason="stop-loss")
    (t,) = paper_trades(db, sym, iv)
    assert t["bars"] == 3 and abs(t["mfe"] - 0.04) < 1e-9 and abs(t["mae"] - (-0.05)) < 1e-9
    assert t["reason"] == "stop-loss" and t["net"] == -3.0
    assert abs(t["signal"]["atr_pct"] - 0.01) < 1e-9 and t["signal"]["volume_ratio"] == 2.0
    d = diagnose_trades([t], 0.0028)                           # the shared diagnosis accepts paper trades
    assert d["trades"] == 1 and d["fast_stops"] == 1.0


def test_open_position_is_not_a_trade_yet(db):
    _fill(db, STEP, "BUY", 100.0)
    assert paper_trades(db, "BTCUSDT", 15) == []
