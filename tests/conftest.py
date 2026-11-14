import pytest

from trading_bot.config import load_config
from trading_bot.db import Database
from trading_bot.portfolio import Portfolio


@pytest.fixture
def cfg():
    return load_config("local_sim")


@pytest.fixture
def db():
    d = Database(":memory:")
    yield d
    d.close()


@pytest.fixture
def pf(cfg):
    return Portfolio(100.0, cfg.costs, cfg.exchange_rules)
