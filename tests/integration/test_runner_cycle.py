"""Drives the real Runner buy -> hold -> sell cycle with a stub price feed (no network)."""
import pytest

from trading_bot.config import load_config
from trading_bot.features import Feature
from trading_bot.models import Candle, Quote, now_ms
from trading_bot.runner import Runner


class StubFeed:
    def __init__(self, bid=60_000.0, ask=60_005.0):
        self.q = Quote(bid, ask, now_ms())
        self.stale = False

    def get_quote(self):
        return Quote(self.q.bid, self.q.ask, now_ms())

    def is_stale(self):
        return self.stale

    def stop(self):
        pass


def feat(atr=100.0):
    return Feature(0, 900_000, 60_000, 60_100, 59_900, 60_000, 10, 60, atr, 5, 2, 1)


@pytest.fixture
def runner(tmp_path):
    cfg = load_config("local_sim")
    cfg.data.db_path = str(tmp_path / "t.db")
    r = Runner(cfg)
    r.feed = StubFeed()
    return r


def test_full_trade_cycle(runner):
    r = runner
    candle = Candle(0, 60_000, 60_100, 59_900, 60_000, 10)
    r._enter(feat(), candle, None)
    assert r.pos is not None and r.pf.base > 0
    assert r.pos.stop < r.pos.entry_price < r.pos.target
    assert r.pf.base * r.pos.entry_price <= r.pf.equity(60_000) * 0.95 + 1e-6

    # price falls through the stop -> live watcher sells
    r.feed.q = Quote(r.pos.stop - 10, r.pos.stop - 5, now_ms())
    r._watch_price()
    assert r.pos is None and r.pf.base == 0
    assert r.db.get_state("position") is None
    n = r.db.conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0]
    assert n == 2
    gross, net = r.db.conn.execute(
        "SELECT realized_gross, realized_net FROM fills WHERE side='SELL'").fetchone()
    assert float(net) < float(gross) < 0           # a loss, and costs made it worse


def test_state_survives_restart(runner, tmp_path):
    r = runner
    r._enter(feat(), Candle(0, 60_000, 60_100, 59_900, 60_000, 10), None)
    r._save_state()
    pos, base = r.pos, r.pf.base
    r.db.close()
    cfg = load_config("local_sim")
    cfg.data.db_path = str(tmp_path / "t.db")
    r2 = Runner(cfg)
    r2._restore_state()
    assert r2.pos == pos and r2.pf.base == pytest.approx(base)


def test_blocked_when_kill_switch_on(runner):
    runner.db.set_state("kill_switch", True)
    runner._enter(feat(), Candle(0, 60_000, 60_100, 59_900, 60_000, 10), None)
    assert runner.pos is None and runner.pf.base == 0


def test_blocked_when_spread_too_wide(runner):
    runner.feed.q = Quote(60_000, 60_100, now_ms())     # 0.17% > 0.05% limit
    runner._enter(feat(), Candle(0, 60_000, 60_100, 59_900, 60_000, 10), None)
    assert runner.pos is None


def test_kill_switch_closes_position(runner):
    runner._enter(feat(), Candle(0, 60_000, 60_100, 59_900, 60_000, 10), None)
    assert runner.pos
    runner.db.set_state("kill_switch", True)
    runner._poll_controls()
    assert runner.pos is None
