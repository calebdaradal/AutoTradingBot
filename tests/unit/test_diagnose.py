"""Track B tests: diagnosis facts, the locked v1.0 baseline, the hypothesis rules, and the final-test guard."""
import json

import pytest

from trading_bot import candidates as cand
from trading_bot import hypotheses as hy
from trading_bot.backtest import run_backtest
from trading_bot.candidates import BASELINE_VERSION, build_baseline, build_candidate, candidate
from trading_bot.diagnose import diagnose_trades, load_trades
from trading_bot.research import FinalTestError, check_final_test, dataset_info, record_experiment
from trading_bot.strategies import TrendMomentum
from tests.unit.test_backtest import BAR0, BAR1, story


def _t(net, reason, mfe=0.01, mae=-0.003, bars=5, signal=None):
    return {"net": net, "gross": net + 0.01, "reason": reason, "mfe": mfe, "mae": mae, "bars": bars, "signal": signal}


@pytest.fixture
def sandbox():
    """A temporary candidate in the registry so tests never leave junk behind."""
    saved = dict(cand._REGISTRY)
    @candidate("test_idea-0.1")
    class Idea(TrendMomentum):
        pass
    yield "test_idea-0.1"
    cand._REGISTRY.clear()
    cand._REGISTRY.update(saved)


GOOD = {"trades": 30, "net_return": 0.05, "profit_factor": 1.5, "max_drawdown": 0.05, "buy_hold_return": 0.0}


# ------------------------------------------------------------------ baseline lock
def test_baseline_v1_parameters_are_locked(cfg):
    s = cfg.strategy
    assert (s.name, s.version) == ("trend_momentum", "1.0")
    assert (s.ema_fast, s.ema_slow, s.rsi_period, s.rsi_min, s.rsi_max) == (20, 50, 14, 50, 70)
    assert (s.atr_period, s.volume_ma_period, s.volume_mult) == (14, 20, 1.0)
    assert (s.atr_pct_min, s.atr_pct_max, s.stop_atr_mult, s.target_atr_mult) == (0.0015, 0.02, 2.0, 3.0)
    assert (s.max_hold_bars, s.max_trades_per_day, s.cooldown_bars) == (48, 3, 4)


def test_baseline_is_the_plain_strategy_and_cannot_be_registered_again(cfg):
    assert build_baseline(cfg.strategy).version == BASELINE_VERSION
    with pytest.raises(ValueError):
        candidate(BASELINE_VERSION)(TrendMomentum)


def test_baseline_cannot_be_a_candidate_or_get_a_final_test(db, cfg):
    with pytest.raises(hy.HypothesisError):
        hy.add_hypothesis(db, title="t", statement="s", prediction="p", candidate=BASELINE_VERSION)
    with pytest.raises(hy.HypothesisError, match="permanent baseline"):
        hy.require_final_ready(db, BASELINE_VERSION)


# ------------------------------------------------------------------ diagnosis
def test_diagnose_counts_exit_reasons_and_costs():
    trades = [_t(-1, "stop-loss", mfe=0.001, bars=2), _t(-1, "stop-loss", mfe=0.02, bars=10),
              _t(2, "target reached", mfe=0.03), _t(-0.1, "held too long", mfe=0.0001)]
    d = diagnose_trades(trades, 0.0028)
    assert d["trades"] == 4 and d["win_rate"] == 0.25
    assert d["by_reason"]["stop-loss"]["n"] == 2 and d["by_reason"]["stop-loss"]["wins"] == 0
    assert d["by_reason"]["target reached"]["net"] == 2
    assert d["never_paid_costs"] == 0.5            # two of four never rose 0.28%
    assert d["fast_stops"] == 0.25                 # one stop inside 4 candles
    assert d["losers_that_were_up"] == pytest.approx(1 / 3)


def test_diagnose_handles_no_trades():
    d = diagnose_trades([], 0.0028)
    assert d["trades"] == 0 and d["win_rate"] is None


def test_diagnose_compares_entry_signals():
    sig = lambda rsi: {"rsi": rsi, "atr_pct": 0.005, "volume_ratio": 1.2, "trend_gap_pct": 0.01}
    d = diagnose_trades([_t(1, "target reached", signal=sig(60)), _t(-1, "stop-loss", signal=sig(55))], 0.0028)
    assert d["signal_winners"]["rsi"] == 60 and d["signal_losers"]["rsi"] == 55


def _result(cfg, strat=None):
    entry, feats = story([BAR0, BAR1, (101, 101, 101, 101), (101, 101, 101, 101)])
    return run_backtest(entry, [], cfg, 1000.0, feats=feats, strat=strat), entry


def test_load_trades_reads_latest_saved_backtest(db, cfg):
    assert load_trades(db, BASELINE_VERSION) == {"train": [], "validation": []}
    res, entry = _result(cfg)
    record_experiment(db, kind="backtest", label="train", cfg=cfg, strategy_version=BASELINE_VERSION,
                      dataset=dataset_info(entry), result=res, batch=1)
    record_experiment(db, kind="backtest", label="train", cfg=cfg, strategy_version="other-1.0",
                      dataset=dataset_info(entry), result=res, batch=1)
    got = load_trades(db, BASELINE_VERSION)
    assert got["train"] == json.loads(json.dumps(res.trades)) and got["validation"] == []


def test_backtest_runs_a_candidate_strategy_instead_of_v1(cfg):
    class NeverBuys(TrendMomentum):
        def evaluate(self, f, pos, ctx):
            from trading_bot.strategies import HOLD, Decision
            return Decision(HOLD, ["never"])
    base, _ = _result(cfg)
    none, _ = _result(cfg, strat=NeverBuys(cfg.strategy))
    assert len(base.trades) >= 1 and len(none.trades) == 0


# ------------------------------------------------------------------ hypotheses
def _add(db, cand_id, **kw):
    return hy.add_hypothesis(db, title="wait for a dip", statement="Buying after a small dip loses less",
                             prediction="Fewer quick stop-outs", candidate=cand_id, **kw)


def test_hypothesis_needs_all_text_and_a_registered_candidate(db, sandbox):
    with pytest.raises(hy.HypothesisError):
        hy.add_hypothesis(db, title="", statement="s", prediction="p", candidate=sandbox)
    with pytest.raises(hy.HypothesisError, match="not registered"):
        _add(db, "nope-1.0")
    assert hy.list_hypotheses(db) == []


def test_only_one_open_hypothesis_at_a_time(db, sandbox):
    h = _add(db, sandbox)
    assert h["id"] == "H1" and h["state"] == "DRAFT" and h["history"][0]["reason"]
    with pytest.raises(hy.HypothesisError, match="one idea at a time"):
        _add(db, sandbox)
    hy.close_hypothesis(db, "H1", "changed my mind")
    assert _add(db, sandbox)["id"] == "H2"


def test_passing_train_and_validation_qualifies_then_final_test_is_allowed_once(db, sandbox):
    _add(db, sandbox)
    h = hy.record_dev_results(db, "H1", {"train": GOOD, "validation": GOOD})
    assert h["state"] == "QUALIFIED_CANDIDATE"
    assert hy.require_final_ready(db, sandbox)["id"] == "H1"
    h = hy.record_final_result(db, "H1", GOOD, 7)
    assert h["state"] == "QUALIFIED_CANDIDATE" and h["final"]["passed"]
    with pytest.raises(hy.HypothesisError, match="already took"):
        hy.require_final_ready(db, sandbox)
    assert hy.open_hypothesis(db) is None          # finished, so a new idea may start


def test_failing_validation_rejects_and_blocks_the_final_test(db, sandbox):
    _add(db, sandbox)
    bad = dict(GOOD, net_return=-0.02, profit_factor=0.6)
    h = hy.record_dev_results(db, "H1", {"train": GOOD, "validation": bad})
    assert h["state"] == "REJECTED" and "validation" in h["history"][-1]["reason"]
    with pytest.raises(hy.HypothesisError, match="REJECTED"):
        hy.require_final_ready(db, sandbox)


def test_same_hypothesis_cannot_be_retested_after_judgement(db, sandbox):
    _add(db, sandbox)
    hy.record_dev_results(db, "H1", {"train": GOOD, "validation": GOOD})
    with pytest.raises(hy.HypothesisError, match="already judged"):
        hy.record_dev_results(db, "H1", {"train": GOOD, "validation": GOOD})


def test_failed_final_test_rejects(db, sandbox):
    _add(db, sandbox)
    hy.record_dev_results(db, "H1", {"train": GOOD, "validation": GOOD})
    h = hy.record_final_result(db, "H1", dict(GOOD, net_return=-0.01), 8)
    assert h["state"] == "REJECTED" and not h["final"]["passed"]


def test_judge_flags_each_failure_and_too_few_trades():
    t = {"min_profit_factor": 1.2, "min_trades": 20, "min_return": 0.0, "max_drawdown": 0.15}
    assert hy.judge(t, GOOD) == []
    assert len(hy.judge(t, dict(GOOD, trades=5))) == 1
    assert len(hy.judge(t, dict(GOOD, max_drawdown=0.3))) == 1
    assert hy.judge(t, dict(GOOD, profit_factor=None)) == []       # no losing trades at all


def test_thresholds_are_fixed_at_creation(db, sandbox):
    h = _add(db, sandbox, min_profit_factor=1.5, min_trades=10)
    assert h["thresholds"]["min_profit_factor"] == 1.5 and h["thresholds"]["min_trades"] == 10
    assert hy.get_hypothesis(db, "H1")["thresholds"] == h["thresholds"]


def test_missing_candidate_is_reported_clearly(cfg):
    with pytest.raises(KeyError, match="Unknown candidate"):
        build_candidate("ghost-9.9", cfg.strategy)


def test_final_test_is_per_strategy_version(db, cfg):
    res, entry = _result(cfg)
    record_experiment(db, kind="final_test", label="final", cfg=cfg, strategy_version="a-1.0",
                      dataset=dataset_info(entry), result=res, batch=1)
    with pytest.raises(FinalTestError):
        check_final_test(db, cfg, res.start_ms, res.end_ms, "a-1.0")
    assert check_final_test(db, cfg, res.start_ms, res.end_ms, "b-1.0")["prior_looks"] == 1   # different idea: allowed
