"""Track B: why does a strategy lose money? Reads the saved trades of a past backtest and reports FACTS only.

Facts here are measured numbers. Explanations and ideas belong in a hypothesis (hypotheses.py), never here.
"""
import json
from statistics import mean

from .candidates import BASELINE_VERSION  # noqa: F401  (re-exported for the CLI)


def load_trades(db, version: str, labels=("train", "validation")) -> dict:
    """Trades from the most recent saved backtest of each period. {label: [trade, ...]}"""
    out = {}
    for lab in labels:
        row = db.conn.execute(
            "SELECT trades_json FROM experiments WHERE kind='backtest' AND label=? AND strategy_version=? "
            "AND trades_json IS NOT NULL ORDER BY id DESC LIMIT 1", (lab, version)).fetchone()
        out[lab] = json.loads(row["trades_json"]) if row else []
    return out


def _avg(xs):
    return mean(xs) if xs else None


def diagnose_trades(trades: list, round_trip_cost: float) -> dict:
    """round_trip_cost: fraction of price lost to fees + spread + slippage on a buy-then-sell (e.g. 0.0028)."""
    n = len(trades)
    wins = [t for t in trades if t["net"] > 0]
    losses = [t for t in trades if t["net"] <= 0]
    by_reason = {}
    for t in trades:
        g = by_reason.setdefault(t["reason"], {"n": 0, "wins": 0, "net": 0.0, "bars": []})
        g["n"] += 1
        g["wins"] += t["net"] > 0
        g["net"] += t["net"]
        g["bars"].append(t["bars"])
    for g in by_reason.values():
        g["avg_bars"] = _avg(g.pop("bars"))

    def sig(group, key):
        return _avg([t["signal"][key] for t in group if t.get("signal") and t["signal"].get(key) is not None])

    return {
        "trades": n,
        "win_rate": len(wins) / n if n else None,
        "gross_pnl": sum(t["gross"] for t in trades), "net_pnl": sum(t["net"] for t in trades),
        "by_reason": by_reason,
        # entries that never moved clearly in our favour (not even enough to pay the trading costs)
        "never_paid_costs": sum(t["mfe"] < round_trip_cost for t in trades) / n if n else None,
        # entries that dropped quickly: a stop hit within 4 candles (1 hour)
        "fast_stops": sum(t["reason"] == "stop-loss" and t["bars"] <= 4 for t in trades) / n if n else None,
        "avg_mfe_winners": _avg([t["mfe"] for t in wins]), "avg_mfe_losers": _avg([t["mfe"] for t in losses]),
        "avg_mae_winners": _avg([t["mae"] for t in wins]), "avg_mae_losers": _avg([t["mae"] for t in losses]),
        "avg_bars_winners": _avg([t["bars"] for t in wins]), "avg_bars_losers": _avg([t["bars"] for t in losses]),
        # the loser group had good moves too and then gave them back
        "losers_that_were_up": sum(t["mfe"] >= round_trip_cost for t in losses) / len(losses) if losses else None,
        "signal_winners": {k: sig(wins, k) for k in ("rsi", "atr_pct", "volume_ratio", "trend_gap_pct")},
        "signal_losers": {k: sig(losses, k) for k in ("rsi", "atr_pct", "volume_ratio", "trend_gap_pct")},
    }


def _pct(x):
    return "n/a" if x is None else f"{x:.1%}"


def print_diagnosis(label: str, d: dict, say):
    if not d["trades"]:
        say(f"[{label}] no saved trades. Run 'backtest' first.")
        return
    say(f"[{label}] {d['trades']} trades, win rate {_pct(d['win_rate'])}, profit before costs {d['gross_pnl']:+.4f} USDT, "
        f"after costs {d['net_pnl']:+.4f} USDT")
    for reason, g in sorted(d["by_reason"].items(), key=lambda x: x[1]["net"]):
        say(f"[{label}] exit '{reason}': {g['n']} trades, {g['wins']} won, total {g['net']:+.4f} USDT, "
            f"held {g['avg_bars']:.0f} candles on average")
    say(f"[{label}] entries that never rose enough to pay the costs: {_pct(d['never_paid_costs'])} | "
        f"stopped out within 1 hour: {_pct(d['fast_stops'])} | losers that were up first: {_pct(d['losers_that_were_up'])}")
    say(f"[{label}] best point reached: winners {_pct(d['avg_mfe_winners'])} vs losers {_pct(d['avg_mfe_losers'])} | "
        f"worst dip: winners {_pct(d['avg_mae_winners'])} vs losers {_pct(d['avg_mae_losers'])}")
    sw, sl = d["signal_winners"], d["signal_losers"]
    if sw["rsi"] is not None and sl["rsi"] is not None:
        say(f"[{label}] entry signals winners vs losers: momentum (RSI) {sw['rsi']:.1f} vs {sl['rsi']:.1f}, "
            f"swing size {sw['atr_pct']:.2%} vs {sl['atr_pct']:.2%}, volume {sw['volume_ratio']:.2f}x vs {sl['volume_ratio']:.2f}x, "
            f"1h trend gap {sw['trend_gap_pct']:.2%} vs {sl['trend_gap_pct']:.2%}")
