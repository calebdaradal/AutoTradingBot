"""Command-line entry point:  python -m trading_bot <command>

  sync        download recent price history and check it for gaps
  backtest    replay the strategy on past data (train / validation / test + cost stress)
  run         start paper trading (fake money, real prices)
  status      show how the paper run is doing
  kill        emergency stop: block new buys and close any open position
  resume      clear the emergency stop / drawdown halt
  dashboard   open the visual dashboard (browser)
"""
import argparse
import subprocess
import sys

from . import log
from .config import DEFAULT_PROFILE, PROFILES, ROOT, load_config, starting_balance_usdt
from .data.bybit import BybitPublic
from .data.sync import quality_report, repair_gaps, sync_history
from .db import Database


def cmd_sync(cfg, a):
    db = Database(cfg.data.db_path)
    client = BybitPublic(cfg.data.rest_url, cfg.category, cfg.symbol)
    for iv in (cfg.data.entry_interval, cfg.data.trend_interval):
        sync_history(client, db, cfg.symbol, iv, a.days)
        repair_gaps(client, db, cfg.symbol, iv)
        q = quality_report(db, cfg.symbol, iv)
        (log.ok if q["gaps"] == 0 else log.warn)(f"{iv}m data quality: {q['count']} candles, {q['gaps']} gaps")
    log.ok("Sync finished")


def cmd_backtest(cfg, a):
    from .backtest import run_backtest, split_ranges, with_overrides
    db = Database(cfg.data.db_path)
    entry = db.load_candles(cfg.symbol, cfg.data.entry_interval)
    trend = db.load_candles(cfg.symbol, cfg.data.trend_interval)
    if len(entry) < 1000:
        log.error(f"Only {len(entry)} 15m candles stored; run 'sync --days 180' first")
        return
    start = starting_balance_usdt(cfg)
    log.ok(f"Backtest on {len(entry)} candles ({len(entry) / 96:.0f} days), start {start:.2f} USDT")
    from .features import build_features
    feats = build_features(entry, trend, cfg.strategy, cfg.data.entry_interval, cfg.data.trend_interval)
    ranges = split_ranges(len(entry), cfg)
    ranges["ALL"] = (0, len(entry))
    for name, (lo, hi) in ranges.items():
        r = run_backtest(entry, trend, cfg, start, lo, hi, name, feats)
        for line in r.summary_lines():
            log.note(line)
        if r.blocked and name == "ALL":
            log.note("  Most common blocks: " + ", ".join(f"{k} ({v})" for k, v in
                                                           sorted(r.blocked.items(), key=lambda x: -x[1])[:3]))
    log.note("--- Stress test: what if trading costs are higher? (all data) ---")
    for mult in (1.0, 2.0, 3.0):
        c2 = with_overrides(cfg, cost_mult=mult)
        r = run_backtest(entry, trend, c2, start, 0, len(entry), f"costs x{mult:g}")
        log.note(f"costs x{mult:g}: result {r.net_return:+.2%}, {len(r.trades)} trades, max drop {r.max_drawdown:.2%}")
    log.note("--- Sensitivity: do small setting changes flip the result? (all data) ---")
    s = cfg.strategy
    variants = {
        "RSI floor -5": {"rsi_min": s.rsi_min - 5}, "RSI floor +5": {"rsi_min": s.rsi_min + 5},
        "stop 1.5x ATR": {"stop_atr_mult": 1.5}, "stop 2.5x ATR": {"stop_atr_mult": 2.5},
        "target 2x ATR": {"target_atr_mult": 2.0}, "target 4x ATR": {"target_atr_mult": 4.0},
    }
    for name, ov in variants.items():
        c2 = with_overrides(cfg, strategy=ov)
        f2 = build_features(entry, trend, c2.strategy, cfg.data.entry_interval, cfg.data.trend_interval)
        r = run_backtest(entry, trend, c2, start, 0, len(entry), name, f2)
        log.note(f"{name}: result {r.net_return:+.2%}, {len(r.trades)} trades")
    log.ok("Backtest finished. Remember: past results do not promise future results.")


def cmd_run(cfg, a):
    from .runner import Runner
    Runner(cfg, heartbeat_seconds=a.heartbeat).run(minutes=a.minutes)


def cmd_status(cfg, a):
    from .report import print_report, paper_report
    db = Database(cfg.data.db_path)
    print_report(paper_report(db, starting_balance_usdt(cfg)), log.note)
    log.note(f"Emergency stop: {'ON' if db.get_state('kill_switch', False) else 'off'}")


def cmd_kill(cfg, a):
    Database(cfg.data.db_path).set_state("kill_switch", True)
    log.warn("Emergency stop set. The running bot will close any open position and stop buying.")


def cmd_resume(cfg, a):
    db = Database(cfg.data.db_path)
    db.set_state("kill_switch", False)
    db.set_state("clear_halt", True)
    log.ok("Emergency stop and drawdown halt cleared (takes effect within seconds if the bot is running).")


def cmd_dashboard(cfg, a):
    log.ok("Opening dashboard (Ctrl+C to close)")
    # --browser.gatherUsageStats false also skips Streamlit's first-run email prompt
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ROOT / "src" / "trading_bot" / "dashboard.py"),
                    "--browser.gatherUsageStats", "false", "--server.port", "8501",
                    "--", "--profile", a.profile])


def main(argv=None):
    p = argparse.ArgumentParser(prog="trading_bot", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", default=DEFAULT_PROFILE, choices=PROFILES)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync"); s.add_argument("--days", type=float, default=180); s.set_defaults(fn=cmd_sync)
    sub.add_parser("backtest").set_defaults(fn=cmd_backtest)
    r = sub.add_parser("run")
    r.add_argument("--minutes", type=float, default=None, help="stop after N minutes (default: run until Ctrl+C)")
    r.add_argument("--heartbeat", type=int, default=60, help="seconds between status lines")
    r.set_defaults(fn=cmd_run)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("kill").set_defaults(fn=cmd_kill)
    sub.add_parser("resume").set_defaults(fn=cmd_resume)
    sub.add_parser("dashboard").set_defaults(fn=cmd_dashboard)
    a = p.parse_args(argv)
    log.setup(str(ROOT / "logs"))
    try:
        cfg = load_config(a.profile)
        a.fn(cfg, a)
    except KeyboardInterrupt:
        log.note("Interrupted")
    except Exception as e:
        log.error(f"{type(e).__name__}: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
