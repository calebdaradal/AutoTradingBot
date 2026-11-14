"""Research bookkeeping: experiment records, the protected final test, and the paper-config freeze.

Plain meaning:
  * Experiment record = a saved receipt of every backtest (settings, data used, code version, results).
  * Final test       = the last 25% of history, kept as a "final exam". It can be taken once per setup.
  * Config freeze    = the paper bot remembers its exact settings and refuses to start if they change.
"""
import hashlib
import json
import subprocess
from pathlib import Path

from .config import ROOT
from .models import now_ms

# Settings that decide how the bot trades. Changing any of these means "a different bot".
FROZEN_SECTIONS = ("symbol", "category", "mode", "trading_enabled", "account", "costs",
                   "exchange_rules", "strategy", "risk")
FROZEN_DATA_KEYS = ("entry_interval", "trend_interval")


class ConfigFrozenError(Exception):
    pass


class FinalTestError(Exception):
    pass


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


# ------------------------------------------------------------------ fingerprints
def config_sections(cfg) -> dict:
    """The trading-relevant part of the config, split by section."""
    raw = cfg.raw
    out = {k: raw.get(k) for k in FROZEN_SECTIONS}
    out["data"] = {k: raw["data"].get(k) for k in FROZEN_DATA_KEYS}
    return out


def config_hash(cfg) -> str:
    return _hash(config_sections(cfg))[:16]


def dataset_info(candles) -> dict:
    """Which candles were used: how many, from when to when, and a checksum (a fingerprint of the numbers)."""
    h = hashlib.sha256()
    for c in candles:
        h.update(f"{c.start},{c.open},{c.high},{c.low},{c.close},{c.volume};".encode())
    return {"candles": len(candles), "start_ms": candles[0].start if candles else None,
            "end_ms": candles[-1].start if candles else None, "hash": h.hexdigest()[:16]}


def git_info(root: Path = ROOT) -> dict:
    """Which version of the code ran. Never fails: returns 'unknown' if git is unavailable."""
    def run(*args):
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10)
    try:
        commit = run("rev-parse", "--short", "HEAD")
        if commit.returncode != 0:
            return {"commit": "unknown", "dirty": None}
        dirty = bool(run("status", "--porcelain").stdout.strip())
        return {"commit": commit.stdout.strip(), "dirty": dirty}
    except Exception:
        return {"commit": "unknown", "dirty": None}


# ------------------------------------------------------------------ experiment records
def record_experiment(db, *, kind, label, cfg, strategy_version, dataset, result, batch,
                      include_trades=True, note="") -> int:
    git = git_info()
    cur = db.conn.execute(
        "INSERT INTO experiments(ts_ms,batch,kind,label,strategy_version,config_hash,config_json,git_commit,"
        "git_dirty,data_start_ms,data_end_ms,candles,dataset_hash,metrics_json,trades_json,note) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (now_ms(), batch, kind, label, strategy_version, config_hash(cfg),
         json.dumps(config_sections(cfg), default=str, sort_keys=True), git["commit"],
         None if git["dirty"] is None else int(git["dirty"]),
         result.start_ms, result.end_ms, dataset["candles"], dataset["hash"],
         json.dumps(result.metrics()), json.dumps(result.trades) if include_trades else None, note))
    return cur.lastrowid


def recent_experiments(db, limit=15):
    return db.conn.execute(
        "SELECT id,ts_ms,kind,label,strategy_version,config_hash,git_commit,git_dirty,metrics_json "
        "FROM experiments ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


# ------------------------------------------------------------------ protected final test
def check_final_test(db, cfg, test_start_ms, test_end_ms, strategy_version=None) -> dict:
    """Decide if the final exam may be taken now. Raises FinalTestError if not allowed.
    Returns {'prior_looks': n} - how many times these test dates were already used.
    Same settings AND same strategy version (when given) count as 'the same setup'."""
    chash = config_hash(cfg)
    prior = db.conn.execute(
        "SELECT config_hash, strategy_version, data_start_ms, data_end_ms FROM experiments "
        "WHERE kind='final_test'").fetchall()
    overlapping = [p for p in prior if p["data_start_ms"] <= test_end_ms and p["data_end_ms"] >= test_start_ms]
    if any(p["config_hash"] == chash and (strategy_version is None or p["strategy_version"] == strategy_version)
           for p in overlapping):
        raise FinalTestError("The final test was already taken for these exact settings and dates. "
                             "Re-running it would not be honest. Change the strategy version and get "
                             "fresh data first.")
    return {"prior_looks": len(overlapping)}


# ------------------------------------------------------------------ paper config freeze
def freeze_config(db, cfg, reason="first start") -> dict:
    sections = config_sections(cfg)
    rec = {"hash": config_hash(cfg), "sections": {k: _hash(v)[:8] for k, v in sections.items()},
           "frozen_ms": now_ms(), "reason": reason, "git": git_info()["commit"]}
    history = db.get_state("config_freeze_history", [])
    history.append({k: rec[k] for k in ("hash", "frozen_ms", "reason")})
    db.set_state("config_freeze_history", history)
    db.set_state("frozen_config", rec)
    return rec


def check_config_freeze(db, cfg) -> str:
    """Returns 'frozen' (first start, now locked) or 'matches'. Raises ConfigFrozenError if settings changed."""
    saved = db.get_state("frozen_config")
    if not saved:
        freeze_config(db, cfg)
        return "frozen"
    now = {k: _hash(v)[:8] for k, v in config_sections(cfg).items()}
    changed = sorted(k for k in now if now[k] != saved["sections"].get(k))
    if changed or config_hash(cfg) != saved["hash"]:
        raise ConfigFrozenError(
            f"Settings changed since the paper run was frozen (changed: {', '.join(changed) or 'unknown'}). "
            f"Undo the edit, or run 'refreeze --reason \"why\"' to accept the new settings "
            f"(this should be treated as a NEW experiment).")
    return "matches"
