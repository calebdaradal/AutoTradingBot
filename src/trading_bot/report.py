"""Reads the paper-trading journal and produces the numbers that answer: "is this working?"."""
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
    return {
        "days_running": days, "start_equity": start_equity, "equity": cur, "return": cur / start_equity - 1,
        "closed_trades": len(sells), "win_rate": wins / len(sells) if sells else 0.0,
        "gross_pnl": gross, "net_pnl": net, "fees": fees, "max_drawdown": worst, "buy_hold": bh,
        "decisions": n_dec, "blocked_top": blocked, "errors": errors,
    }


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
    say(f"Worst drop from a peak: {r['max_drawdown']:.2%}")
    for b in r["blocked_top"]:
        say(f"Often blocked by: {b['reasons']} ({b['n']}x)")
    say("Verdict: " + verdict(r))
