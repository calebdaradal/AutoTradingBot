"""Read-only dashboard. Run with:  python -m trading_bot dashboard
It only READS the journal; it cannot place trades. Refreshes itself every few seconds."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `trading_bot` imports work under streamlit

import pandas as pd
import streamlit as st

from trading_bot import hypotheses as hy
from trading_bot.config import DEFAULT_PROFILE, load_config, starting_balance_usdt
from trading_bot.db import Database
from trading_bot.diagnose import diagnose_trades, print_diagnosis
from trading_bot.ops import GATE_DAYS, GATE_TRADES, ops_flags, ops_report
from trading_bot.report import paper_report, paper_trades, verdict
from trading_bot.research import invalid_experiments

REFRESH_SECONDS = 10

p = argparse.ArgumentParser()
p.add_argument("--profile", default=DEFAULT_PROFILE)
args, _ = p.parse_known_args(sys.argv[1:])

cfg = load_config(args.profile)
db = Database(cfg.data.db_path)
start = starting_balance_usdt(cfg)

st.set_page_config(page_title="Paper Trading Dashboard", layout="wide")
st.title("Paper trading dashboard (pretend money)")
st.caption(f"Real market prices, fake money. Nothing here can place a real order. "
           f"Updates by itself every {REFRESH_SECONDS} seconds.")


@st.fragment(run_every=REFRESH_SECONDS)
def live_view():
    r = paper_report(db, start)

    if db.get_state("kill_switch", False):
        st.error("EMERGENCY STOP is ON - the bot will not buy.")
    risk = db.get_state("risk") or {}
    if risk.get("halted"):
        st.error(f"HALTED: {risk['halted']}. Run `python -m trading_bot resume` after you review.")

    c = st.columns(5)
    c[0].metric("Account (USDT)", f"{r['equity']:.3f}", f"{r['return']:+.2%}")
    c[1].metric("Closed trades", r["closed_trades"])
    c[2].metric("Win rate", f"{r['win_rate']:.0%}")
    c[3].metric("Worst drop", f"{r['max_drawdown']:.2%}")
    c[4].metric("Days running", f"{r['days_running']:.1f}")
    n = lambda v, f: "n/a" if v is None else f.format(v)  # noqa: E731
    c = st.columns(5)
    c[0].metric("Profit factor", n(r["profit_factor"], "{:.2f}"), help="Total won divided by total lost. Above 1.0 = winners outweigh losers.")
    c[1].metric("Average trade (USDT)", n(r["avg_trade"], "{:+.4f}"), help="Average result per closed trade, after costs.")
    c[2].metric("Average win (USDT)", n(r["avg_win"], "{:+.4f}"))
    c[3].metric("Average loss (USDT)", n(r["avg_loss"], "{:+.4f}"))
    c[4].metric("Longest losing streak", r["max_losing_streak"], help="Most losing trades in a row.")
    st.info("Verdict: " + verdict(r))

    ops = ops_report(db, cfg)
    flags = ops_flags(ops)
    gate_done = ops["days_running"] >= GATE_DAYS and ops["closed_trades"] >= GATE_TRADES
    st.subheader("30-day test progress and bot health")
    st.progress(min(1.0, ops["days_running"] / GATE_DAYS),
                text=f"{ops['days_running']:.1f} of {GATE_DAYS} days | {ops['closed_trades']} of {GATE_TRADES} closed trades | "
                     + ("target reached, review the results" if gate_done else "not done yet"))
    for f in flags:
        st.warning(f)
    if not flags:
        st.success("Nothing odd in the bot's health so far.")
    h = st.columns(5)
    h[0].metric("Restarts", ops["restarts"])
    h[1].metric("Missed candles", ops["missed_candles"], help="Price updates (every 15 min) the bot never looked at.")
    h[2].metric("Feed reconnects", ops["feed_reconnects"], help="Times the live price connection dropped and came back.")
    h[3].metric("Stale periods", ops["stale_episodes"], help=f"{ops['stale_seconds']:.0f}s without fresh prices in total.")
    h[4].metric("Rejected orders", ops["orders"].get("REJECTED", 0))
    if ops["avg_slip_bps"] is not None:
        st.write(f"Fill cost vs middle price: average {ops['avg_slip_bps']:.1f} bps, worst {ops['worst_slip_bps']:.1f} bps "
                 f"(the bot assumes {ops['modeled_slip_bps']:.1f}). 1 bps = 0.01%.")
    st.caption(f"Frozen settings id: {ops['frozen_id'] or 'not frozen yet'}. "
               "Any settings change restarts the 30-day clock.")

    pos = db.get_state("position")
    st.subheader("Open position")
    st.write(pos if pos else "None - waiting for a buy signal.")

    eq = pd.DataFrame([dict(x) for x in db.conn.execute("SELECT ts_ms, equity FROM equity ORDER BY id")])
    st.subheader("Account value over time")
    if len(eq):
        eq["time"] = pd.to_datetime(eq["ts_ms"], unit="ms")
        eq["equity"] = eq["equity"].astype(float)
        st.line_chart(eq.set_index("time")["equity"])
    else:
        st.write("No data yet. Start the bot with `python -m trading_bot run`.")

    st.subheader("Profit and costs")
    st.write(f"Before costs {r['gross_pnl']:+.4f} | after costs {r['net_pnl']:+.4f} | fees paid {r['fees']:.4f} USDT")
    if r["buy_hold"] is not None:
        st.write(f"Just holding BTC over the same time: {r['buy_hold']:+.2%}")

    st.subheader("Trades")
    st.dataframe(pd.DataFrame([dict(x) for x in db.conn.execute(
        "SELECT datetime(ts_ms/1000,'unixepoch') AS time, side, qty, price, fee, realized_gross, realized_net, reason "
        "FROM fills ORDER BY id DESC LIMIT 100")]), width='stretch')

    st.subheader("Recent decisions (why the bot did or did not trade)")
    st.dataframe(pd.DataFrame([dict(x) for x in db.conn.execute(
        "SELECT datetime(ts_ms/1000,'unixepoch') AS time, kind, action, reasons FROM decisions "
        "ORDER BY id DESC LIMIT 100")]), width='stretch')

    st.subheader("Warnings and errors")
    st.dataframe(pd.DataFrame([dict(x) for x in db.conn.execute(
        "SELECT datetime(ts_ms/1000,'unixepoch') AS time, level, kind, message FROM events "
        "WHERE level IN ('WARN','ERROR') ORDER BY id DESC LIMIT 50")]), width='stretch')

    st.subheader("Why is it winning or losing? (measured facts, same as `diagnose-paper`)")
    cst = cfg.costs
    lines = []
    print_diagnosis("paper", diagnose_trades(paper_trades(db, cfg.symbol, cfg.data.entry_interval),
                                             2 * (cst.taker_fee + cst.half_spread + cst.slippage)), lines.append)
    st.text("\n".join(lines))

    st.subheader("Strategy research (ideas being tested, separate from this paper run)")
    hyps = hy.list_hypotheses(db)
    if hyps:
        st.dataframe(pd.DataFrame([{"id": x["id"], "idea": x["title"], "version": x["candidate"], "state": x["state"]}
                                   for x in hyps]), width='stretch')
    else:
        st.write("No ideas written down yet.")
    bad = invalid_experiments(db)
    exps = [dict(x) for x in db.conn.execute(
        "SELECT id, datetime(ts_ms/1000,'unixepoch') AS time, kind, label, strategy_version, candles FROM experiments "
        "ORDER BY id DESC LIMIT 30")]
    for e in exps:
        e["status"] = "INVALID TEST" if e["id"] in bad else "ok"
    st.dataframe(pd.DataFrame(exps), width='stretch')


live_view()
