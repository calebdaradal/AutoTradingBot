from trading_bot.features import Feature, build_features, ema, rsi, sma
from trading_bot.models import Candle
from trading_bot.strategies import BUY, HOLD, SELL, Context, TrendMomentum


def test_sma_and_warmup():
    assert sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]


def test_ema_warmup_is_none():
    out = ema(list(range(1, 11)), 5)
    assert out[:4] == [None] * 4 and out[4] == 3.0


def test_rsi_bounds():
    up = rsi([float(i) for i in range(1, 40)], 14)
    assert up[-1] == 100.0
    down = rsi([float(i) for i in range(40, 1, -1)], 14)
    assert down[-1] == 0.0


def _candles(n, minutes, start=0, price=100.0):
    step = minutes * 60_000
    return [Candle(start + i * step, price, price + 1, price - 1, price + i * 0.01, 10.0) for i in range(n)]


def test_no_lookahead_trend_candle(cfg):
    """A 15m bar only sees 1h candles that were already closed when it closed (tiny EMAs used to test)."""
    s = cfg.strategy
    s2 = type(s)(**{**s.__dict__, "ema_fast": 1, "ema_slow": 2})
    trend = [Candle(i * 3_600_000, 1, 1, 1, float(i + 1), 1) for i in range(4)]
    f = build_features(_candles(16, 15), trend, s2)
    assert f[2].trend_slow is None            # closes at 00:45 -> no 1h bar closed yet
    assert f[3].trend_fast == 1.0             # closes at 01:00 -> hour 0 closed (close=1)
    assert f[6].trend_fast == 1.0             # closes at 01:45 -> hour 1 is NOT closed yet
    assert f[7].trend_fast == 2.0             # closes at 02:00 -> hour 1 closed (close=2)


def _feat(**kw):
    base = dict(start=0, close_ms=900_000, open=100, high=101, low=99, close=100, volume=10,
                rsi=60, atr=0.5, vol_ma=5, trend_fast=2, trend_slow=1)
    base.update(kw)
    return Feature(**base)


def test_buy_when_all_conditions_met(cfg):
    d = TrendMomentum(cfg.strategy).evaluate(_feat(), None, Context())
    assert d.action == BUY and d.details["stop"] < 100 < d.details["target"]


def test_hold_reasons(cfg):
    st = TrendMomentum(cfg.strategy)
    assert "1h trend not up" in st.evaluate(_feat(trend_fast=1, trend_slow=2), None, Context()).reasons
    assert st.evaluate(_feat(rsi=80), None, Context()).action == HOLD
    assert st.evaluate(_feat(volume=1), None, Context()).action == HOLD
    assert "market too quiet" in st.evaluate(_feat(atr=0.01), None, Context()).reasons
    assert "market too wild" in st.evaluate(_feat(atr=5), None, Context()).reasons
    assert st.evaluate(_feat(), None, Context(trades_today=99)).action == HOLD
    assert st.evaluate(_feat(), None, Context(bars_since_exit=1)).action == HOLD
    assert st.evaluate(_feat(rsi=None), None, Context()).action == HOLD


def test_exits(cfg):
    st = TrendMomentum(cfg.strategy)
    pos = st.make_position(100, 0.1, 0.5, 0)       # stop 99, target 101.5
    assert st.evaluate(_feat(close=98.9), pos, Context()).reasons == ["stop-loss"]
    assert st.evaluate(_feat(close=101.6), pos, Context()).reasons == ["target reached"]
    assert st.evaluate(_feat(trend_fast=1, trend_slow=2), pos, Context()).reasons == ["1h trend turned down"]
    pos.bars_held = 48
    assert st.evaluate(_feat(), pos, Context()).reasons == ["held too long"]


def test_intrabar_stop_wins_when_both_touched(cfg):
    st = TrendMomentum(cfg.strategy)
    pos = st.make_position(100, 0.1, 0.5, 0)
    assert st.intrabar_exit(98, 103, pos)[0] == "stop-loss"
    assert st.intrabar_exit(99.5, 103, pos)[0] == "target reached"
    assert st.intrabar_exit(99.5, 100.5, pos) is None
