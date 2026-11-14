"""Loads config/base.yaml and merges one profile on top."""
from pathlib import Path
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = "local_sim"
PROFILES = ("local_sim", "live_disabled", "exchange_demo")


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _to_ns(obj):
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _to_ns(v) for k, v in obj.items()})
    return obj


def load_config(profile: str = DEFAULT_PROFILE, config_dir: Path | None = None):
    config_dir = Path(config_dir) if config_dir else ROOT / "config"
    if profile not in PROFILES:
        raise ValueError(f"Unknown profile '{profile}'. Choose one of {PROFILES}")
    base = yaml.safe_load((config_dir / "base.yaml").read_text(encoding="utf-8"))
    over = yaml.safe_load((config_dir / f"{profile}.yaml").read_text(encoding="utf-8")) or {}
    raw = _merge(base, over)
    raw["profile"] = profile
    cfg = _to_ns(raw)
    cfg.raw = raw  # plain dict, saved with every run for the audit trail
    _validate(cfg)
    return cfg


def _validate(cfg):
    """Hard safety rules. These cannot be switched off by editing a profile."""
    if cfg.live_trading_enabled:
        raise ValueError("Live trading is not supported in this project.")
    if cfg.category != "spot":
        raise ValueError("Only spot trading is allowed (no futures/margin/leverage).")
    if cfg.symbol not in cfg.risk.allowed_symbols:
        raise ValueError(f"{cfg.symbol} is not in the allowed symbols list.")
    if cfg.mode == "exchange_demo":
        raise NotImplementedError(
            "Exchange demo mode is Milestone 8 and is not built yet. Use --profile local_sim."
        )
    if cfg.mode != "simulator":
        raise ValueError(f"Unknown mode '{cfg.mode}'.")
    s = cfg.strategy
    if not (0 < cfg.risk.risk_per_trade_pct <= 0.1):
        raise ValueError("risk_per_trade_pct must be between 0 and 10%.")
    if cfg.backtest.train_frac + cfg.backtest.validation_frac >= 1:
        raise ValueError("train_frac + validation_frac must leave room for a test period.")
    if s.ema_fast >= s.ema_slow:
        raise ValueError("ema_fast must be smaller than ema_slow.")


def starting_balance_usdt(cfg) -> float:
    return cfg.account.starting_balance_php / cfg.account.fx_php_per_usdt
