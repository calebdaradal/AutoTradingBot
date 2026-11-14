"""Reads the paper-trading journal and produces the numbers that answer: "is this working?"."""
import json

from .models import now_ms


def paper_report(db, start_equity: float) -> dict:
    c = db.conn
    fills = [dict(r) for r in c.execute("SELECT * FROM fills ORDER BY id")]
    sells = [f for f in fills if f["side"] == "SELL"]
    eq = [dict(r) for r in c.execute("SELECT ts_ms, equity, mark_price FROM equity ORDER BY id")]
    fees = sum(float(f["fee"]) for f in fills)
    gross = sum(float(f["realized_gross"]) for f in sells)
    net = sum(float(f["realized_net"]) for f in sells)
    wins = sum(1 for f in sells if float(f["realized_net"]) > 0)
    cur = float(eq[-1]["equity"]) if eq else start_equity
    peak, worst = start_equity, 0.0
    for r in eq:
        v = float(r["equity"])
        peak = max(peak, v)
        worst = max(worst, 1 - v / peak)
    first_ms = c.execute("SELECT MIN(started_ms) m FROM runs").fetchone()["m"]
    days = (now_ms() - first_ms) / 86_400_000 if first_ms else 0.0
    bh = None
    if len(eq) >= 2:
        bh = float(eq[-1]["mark_price"]) / float(eq[0]["mark_price"]) - 1
    blocked = [dict(r) for r in c.execute(
        "SELECT reasons, COUNT(*) n FROM decisions WHERE kind='blocked' GROUP BY reasons ORDER BY n DESC LIMIT 5")]
    n_dec = c.execute("SELECT COUNT(*) n FROM decisions").fetchone()["n"]
    errors = c.execute("SELECT COUNT(*) n FROM events WHERE level='ERROR'").fetchone()["n"]
    nets = [float(f["realized_net"]) for f in sells]
    won, lost = [x for x in nets if x > 0], [x for x in nets if x <= 0]
    streak = longest = 0
    for x in nets:                                   # longest run of losing trades in a row
        streak = streak + 1 if x <= 0 else 0
        longest = max(longest, streak)
    return {
        "days_running": days, "start_equity": start_equity, "equity": cur, "return": cur / start_equity - 1,
        "closed_trades": len(sells), "win_rate": wins / len(sells) if sells else 0.0,
        "gross_pnl": gross, "net_pnl": net, "fees": fees, "max_drawdown": worst, "buy_hold": bh,
        "decisions": n_dec, "blocked_top": blocked, "errors": errors,
        # profit factor = total won / total lost. Above 1.0 = winners outweigh losers. None = no losers yet.
        "profit_factor": sum(won) / -sum(lost) if lost and sum(lost) < 0 else None,
        "avg_trade": net / len(sells) if sells else None,
        "avg_win": sum(won) / len(won) if won else None,
        "avg_loss": sum(lost) / len(lost) if lost else None,
        "max_losing_streak": longest,
    }


def paper_trades(db, symbol: str, interval: int) -> list:
    """Paper round trips (a BUY and the SELL that closed it) in the same shape the backtest diagnosis uses.
    'bars', 'mfe' (best price vs entry) and 'mae' (worst price vs entry) are measured from the stored candles."""
    c = db.conn
    step = interval * 60_000
    trades, buy = [], None
    for f in c.execute("SELECT * FROM fills ORDER BY id"):
        if f["side"] == "BUY":
            buy = dict(f)
        elif buy is not None:
            entry = float(buy["price"])
            bars = [dict(r) for r in c.execute(
                "SELECT high, low FROM candles WHERE symbol=? AND interval=? AND start_ms>? AND start_ms<=? ORDER BY start_ms",
                (symbol, interval, buy["ts_ms"] - step, f["ts_ms"]))]
            sig = c.execute(
                "SELECT details FROM decisions WHERE kind='signal' AND action='BUY' AND candle_start_ms<=? "
                "ORDER BY candle_start_ms DESC LIMIT 1", (buy["ts_ms"],)).fetchone()
            d = json.loads(sig["details"]) if sig and sig["details"] else {}
            signal = None
            if d.get("close") and d.get("atr") is not None:
                signal = {"rsi": d.get("rsi"), "atr_pct": d["atr"] / d["close"],
                          "volume_ratio": d["volume"] / d["vol_ma"] if d.get("vol_ma") else None,
                          "trend_gap_pct": d["trend_fast"] / d["trend_slow"] - 1 if d.get("trend_slow") else None}
            trades.append({
                "entry_ms": buy["ts_ms"], "exit_ms": f["ts_ms"], "entry": entry, "exit": float(f["price"]),
                "gross": float(f["realized_gross"]), "net": float(f["realized_net"]), "reason": f["reason"] or "unknown",
                "bars": len(bars),
                "mfe": max((b["high"] for b in bars), default=entry) / entry - 1,
                "mae": min((b["low"] for b in bars), default=entry) / entry - 1,
                "signal": signal,
            })
            buy = None
    return trades


def verdict(r: dict) -> str:
    """Plain-language read of the paper run. Deliberately cautious."""
    if r["days_running"] < 30 or r["closed_trades"] < 30:
        return (f"TOO EARLY to judge: {r['days_running']:.1f} of 30 days, {r['closed_trades']} of 30 trades. "
                "Keep it running.")
    if r["net_pnl"] <= 0:
        return "NOT VIABLE so far: lost money after costs. Do not move toward real money."
    if r["buy_hold"] is not None and r["return"] < r["buy_hold"] and r["max_drawdown"] > 0.1:
        return "WEAK: made money but not better than just holding, with large drops. Needs rework."
    return "PROMISING: positive after costs. Keep paper trading and review before any next step."


def print_report(r: dict, say):
    say(f"Running for {r['days_running']:.1f} days | {r['decisions']} decisions logged | {r['errors']} errors")
    say(f"Account: {r['equity']:.3f} USDT (started {r['start_equity']:.3f}) = {r['return']:+.2%}")
    bh = f"{r['buy_hold']:+.2%}" if r["buy_hold"] is not None else "n/a yet"
    say(f"Just holding BTC instead would be: {bh}")
    say(f"Closed trades: {r['closed_trades']} | win rate {r['win_rate']:.0%}")
    say(f"Profit before costs {r['gross_pnl']:+.4f} | after costs {r['net_pnl']:+.4f} | fees {r['fees']:.4f} USDT")
    if r["closed_trades"]:
        pf = f"{r['profit_factor']:.2f}" if r["profit_factor"] is not None else "n/a (no losing trades)"
        aw = f"{r['avg_win']:+.4f}" if r["avg_win"] is not None else "n/a"
        al = f"{r['avg_loss']:+.4f}" if r["avg_loss"] is not None else "n/a"
        say(f"Profit factor {pf} (above 1.0 = winners outweigh losers) | average trade {r['avg_trade']:+.4f} | "
            f"average win {aw} | average loss {al} | longest losing streak {r['max_losing_streak']}")
    say(f"Worst drop from a peak: {r['max_drawdown']:.2%}")
    for b in r["blocked_top"]:
        say(f"Often blocked by: {b['reasons']} ({b['n']}x)")
    say("Verdict: " + verdict(r))
