"""Tests for research bookkeeping: experiment receipts, protected final test, paper-config freeze."""
import copy
import json
import sqlite3

import pytest

from trading_bot.backtest import run_backtest
from trading_bot.research import (ConfigFrozenError, FinalTestError, check_config_freeze, check_final_test,
                                  config_hash, dataset_info, freeze_config, git_info, record_experiment,
                                  recent_experiments)
from trading_bot.runner import Runner
from tests.unit.test_backtest import BAR0, BAR1, story


def _result(cfg):
    entry, feats = story([BAR0, BAR1, (101, 101, 101, 101), (101, 101, 101, 101)])
    return run_backtest(entry, [], cfg, 1000.0, feats=feats), entry


def _record(db, cfg, kind="backtest", label="train"):
    res, entry = _result(cfg)
    return record_experiment(db, kind=kind, label=label, cfg=cfg, strategy_version="t-1.0",
                             dataset=dataset_info(entry), result=res, batch=1)


# ---------------------------------------------------------------- experiment receipts
def test_experiment_is_saved_with_settings_data_and_results(db, cfg):
    _record(db, cfg)
    row = db.conn.execute("SELECT * FROM experiments").fetchone()
    assert row["kind"] == "backtest" and row["label"] == "train"
    assert row["config_hash"] == config_hash(cfg)
    assert row["candles"] == 4 and len(row["dataset_hash"]) == 16
    assert json.loads(row["metrics_json"]) == _result(cfg)[0].metrics()
    assert json.loads(row["config_json"])["strategy"] == cfg.raw["strategy"]
    assert len(recent_experiments(db)) == 1


def test_experiment_receipts_cannot_be_edited_or_deleted(db, cfg):
    _record(db, cfg)
    with pytest.raises(sqlite3.DatabaseError):
        db.conn.execute("UPDATE experiments SET label='x'")
    with pytest.raises(sqlite3.DatabaseError):
        db.conn.execute("DELETE FROM experiments")


def test_dataset_fingerprint_is_stable_and_detects_changes(cfg):
    _, entry = _result(cfg)
    assert dataset_info(entry) == dataset_info(list(entry))
    changed = list(entry)
    changed[1] = type(entry[1])(entry[1].start, entry[1].open, entry[1].high, entry[1].low, 999.0, entry[1].volume)
    assert dataset_info(changed)["hash"] != dataset_info(entry)["hash"]


def test_dataset_info_empty():
    assert dataset_info([])["candles"] == 0


def test_git_info_never_raises(tmp_path):
    out = git_info(tmp_path)                       # not a git repo
    assert out["commit"] == "unknown"


def test_config_hash_ignores_unrelated_settings_but_sees_strategy_changes(cfg):
    h = config_hash(cfg)
    cfg.raw["data"]["db_path"] = "somewhere/else.db"
    assert config_hash(cfg) == h
    cfg.raw["strategy"]["rsi_min"] = cfg.raw["strategy"]["rsi_min"] + 1
    assert config_hash(cfg) != h


# ---------------------------------------------------------------- protected final test
def test_final_test_allowed_once_then_blocked(db, cfg):
    assert check_final_test(db, cfg, 100, 200) == {"prior_looks": 0}
    res, entry = _result(cfg)
    record_experiment(db, kind="final_test", label="test", cfg=cfg, strategy_version="t-1.0",
                      dataset={"candles": 4, "hash": "x"}, result=res, batch=1)
    with pytest.raises(FinalTestError):
        check_final_test(db, cfg, res.start_ms, res.end_ms)


def test_final_test_blocked_even_when_dates_only_overlap(db, cfg):
    res, _ = _result(cfg)
    record_experiment(db, kind="final_test", label="test", cfg=cfg, strategy_version="t-1.0",
                      dataset={"candles": 4, "hash": "x"}, result=res, batch=1)
    with pytest.raises(FinalTestError):
        check_final_test(db, cfg, res.end_ms, res.end_ms + 10_000)


def test_final_test_allowed_for_new_settings_but_counts_prior_looks(db, cfg):
    res, _ = _result(cfg)
    record_experiment(db, kind="final_test", label="test", cfg=cfg, strategy_version="t-1.0",
                      dataset={"candles": 4, "hash": "x"}, result=res, batch=1)
    cfg2 = copy.deepcopy(cfg)
    cfg2.raw["strategy"]["rsi_min"] += 1
    assert check_final_test(db, cfg2, res.start_ms, res.end_ms) == {"prior_looks": 1}


def test_normal_backtests_do_not_use_up_the_final_test(db, cfg):
    _record(db, cfg, kind="backtest", label="validation")
    res, _ = _result(cfg)
    assert check_final_test(db, cfg, res.start_ms, res.end_ms)["prior_looks"] == 0


# ---------------------------------------------------------------- paper config freeze
def test_first_check_freezes_then_matches(db, cfg):
    assert check_config_freeze(db, cfg) == "frozen"
    assert check_config_freeze(db, cfg) == "matches"
    assert db.get_state("frozen_config")["hash"] == config_hash(cfg)


def test_changed_settings_are_refused_and_named(db, cfg):
    check_config_freeze(db, cfg)
    cfg.raw["risk"]["risk_per_trade_pct"] = 0.05
    with pytest.raises(ConfigFrozenError, match="risk"):
        check_config_freeze(db, cfg)


def test_refreeze_accepts_new_settings_and_keeps_history(db, cfg):
    check_config_freeze(db, cfg)
    cfg.raw["strategy"]["rsi_min"] += 1
    freeze_config(db, cfg, reason="testing new idea")
    assert check_config_freeze(db, cfg) == "matches"
    hist = db.get_state("config_freeze_history")
    assert [h["reason"] for h in hist] == ["first start", "testing new idea"]


def test_runner_refuses_to_start_when_settings_changed(cfg, tmp_path):
    cfg.data.db_path = str(tmp_path / "t.db")
    r = Runner(cfg)
    check_config_freeze(r.db, cfg)
    cfg.raw["strategy"]["rsi_min"] += 1
    with pytest.raises(ConfigFrozenError):
        r.start()
    assert r.db.conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0   # nothing started
