"""Read-only dashboard. Run with:  python -m trading_bot dashboard
It only READS the journal; it cannot place trades. Refreshes itself every few seconds."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # so `trading_bot` imports work under streamlit

import pandas as pd
import streamlit as st

from trading_bot.config import DEFAULT_PROFILE, load_config, starting_balance_usdt
from trading_bot.db import Database
from trading_bot.report import paper_report, verdict

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
    st.info("Verdict: " + verdict(r))

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


live_view()
