import pytest

from trading_bot.config import load_config
from trading_bot.models import Quote
from trading_bot.portfolio import OrderRejected, round_down
from trading_bot.risk import RiskManager


def test_round_down():
    assert round_down(0.0012349, 0.000001) == 0.001234


def test_buy_below_min_notional_rejected(pf):
    with pytest.raises(OrderRejected):
        pf.buy(0.00005, 60_000)   # 3 USDT < 5 USDT minimum


def test_cannot_oversell_or_spend_more_than_cash(pf):
    with pytest.raises(OrderRejected):
        pf.sell(0.001, 60_000)
    with pytest.raises(OrderRejected):
        pf.buy(1.0, 60_000)


def test_fees_and_gross_vs_net(pf):
    b = pf.buy(0.001, 60_000)
    s = pf.sell(0.001, 61_000)
    assert s.realized_gross == pytest.approx(1.0)
    assert s.realized_net == pytest.approx(1.0 - b.fee - s.fee)
    assert pf.base == 0 and pf.cash == pytest.approx(100 + s.realized_net)


def test_risk_blocks(cfg):
    rm = RiskManager(cfg.risk, cfg.exchange_rules)
    ok, why = rm.check_entry("BTCUSDT", 10, 10, 1_700_000_000_000)
    assert ok and not why
    assert not rm.check_entry("ETHUSDT", 10, 10, 1_700_000_000_000)[0]
    assert not rm.check_entry("BTCUSDT", 10, 10, 1_700_000_000_000, kill_switch=True)[0]
    assert not rm.check_entry("BTCUSDT", 10, 10, 1_700_000_000_000, data_stale=True)[0]
    assert not rm.check_entry("BTCUSDT", 10, 10, 1_700_000_000_000, trading_enabled=False)[0]
    wide = Quote(100, 101, 0)
    assert not rm.check_entry("BTCUSDT", 10, 10, 1_700_000_000_000, quote=wide)[0]


def test_drawdown_halt_is_sticky(cfg):
    rm = RiskManager(cfg.risk, cfg.exchange_rules)
    assert not rm.check_entry("BTCUSDT", 8, 10, 1_700_000_000_000)[0]
    assert rm.halted
    assert not rm.check_entry("BTCUSDT", 10, 10, 1_700_000_000_000)[0]   # recovered, still halted


def test_loss_streak_cooldown(cfg):
    rm = RiskManager(cfg.risk, cfg.exchange_rules)
    t = 1_700_000_000_000
    for _ in range(cfg.risk.max_consecutive_losses):
        rm.record_trade_result(-1, t)
    assert not rm.check_entry("BTCUSDT", 10, 10, t + 1000)[0]
    assert rm.check_entry("BTCUSDT", 10, 10, t + 13 * 3_600_000)[0]


def test_sizing_respects_cap_and_cash(cfg):
    rm = RiskManager(cfg.risk, cfg.exchange_rules)
    q = rm.size(equity=8.62, cash=8.62, price=60_000, stop=59_500, taker_fee=0.001)
    assert q * 60_000 <= 8.62 * 0.95 + 1e-6
    assert rm.size(8.62, 8.62, 60_000, 61_000, 0.001) == 0.0   # stop above price -> no trade


def test_config_safety(tmp_path):
    cfg = load_config("local_sim")
    assert cfg.live_trading_enabled is False and cfg.category == "spot"
    with pytest.raises(NotImplementedError):
        load_config("exchange_demo")
    with pytest.raises(ValueError):
        load_config("nonsense")
