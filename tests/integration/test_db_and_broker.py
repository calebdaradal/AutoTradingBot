import sqlite3

import pytest

from trading_bot.execution import PaperBroker, load_portfolio, portfolio_state, reconcile
from trading_bot.models import Candle, Quote
from trading_bot.portfolio import Portfolio


def test_candle_dedup(db):
    c = Candle(900_000, 1, 2, 1, 1.5, 3)
    assert db.save_candle("BTCUSDT", 15, c) is True
    assert db.save_candle("BTCUSDT", 15, c) is False
    assert db.candle_bounds("BTCUSDT", 15)[2] == 1


def test_gap_detection(db):
    for i in (0, 1, 3):
        db.save_candle("BTCUSDT", 15, Candle(i * 900_000, 1, 2, 1, 1.5, 3))
    assert db.find_gaps("BTCUSDT", 15) == [2 * 900_000]


def test_journal_is_immutable(db, cfg, pf):
    PaperBroker(cfg, db, pf).submit("A1", "BUY", 0.001, 60_000)
    for sql in ("UPDATE fills SET fee='0'", "DELETE FROM fills", "DELETE FROM orders",
                "UPDATE orders SET status='X'"):
        with pytest.raises(sqlite3.DatabaseError):
            db.conn.execute(sql)


def test_idempotent_order(db, cfg, pf):
    br = PaperBroker(cfg, db, pf)
    assert br.submit("A1", "BUY", 0.001, 60_000).status == "FILLED"
    cash = pf.cash
    assert br.submit("A1", "BUY", 0.001, 60_000).status == "DUPLICATE"
    assert pf.cash == cash and db.conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 1


def test_rejected_order_is_journaled_not_filled(db, cfg, pf):
    r = PaperBroker(cfg, db, pf).submit("A2", "BUY", 0.00001, 60_000)
    assert r.status == "REJECTED" and pf.base == 0
    assert db.conn.execute("SELECT status FROM orders").fetchone()[0] == "REJECTED"


def test_failure_rolls_back_memory_and_db(db, cfg, pf):
    br = PaperBroker(cfg, db, pf)

    def boom(fill):
        raise RuntimeError("disk exploded")

    with pytest.raises(RuntimeError):
        br.submit("A3", "BUY", 0.001, 60_000, extra_state=boom)
    assert pf.cash == 100.0 and pf.base == 0
    assert db.conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
    assert not db.conn.in_transaction


def test_uses_real_quote_prices(db, cfg, pf):
    q = Quote(59_990, 60_010, 0)
    r = PaperBroker(cfg, db, pf).submit("A4", "BUY", 0.001, 60_000, quote=q)
    assert r.fill.price == pytest.approx(60_010 * (1 + cfg.costs.slippage))


def test_restart_reconcile(db, cfg, pf):
    PaperBroker(cfg, db, pf).submit("A5", "BUY", 0.001, 60_000)
    fresh = Portfolio(100.0, cfg.costs, cfg.exchange_rules)
    load_portfolio(fresh, db.get_state("portfolio"))
    assert reconcile(db, fresh) is True
    fresh.cash += 5                                  # simulate corrupted saved state
    assert reconcile(db, fresh) is False
    assert fresh.cash == pytest.approx(pf.cash)      # journal wins
    assert portfolio_state(fresh)["base"] == pf.base
