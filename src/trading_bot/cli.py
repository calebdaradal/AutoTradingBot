"""Command-line entry point:  python -m trading_bot <command>

  sync         download recent price history and check it for gaps
  backtest     replay the strategy on past data (train + validation + stress tests). The final test is LOCKED
  final-check  take the locked final test (once per setup; needs --confirm)
  experiments  list the saved receipts of past backtests
  run          start paper trading (fake money, real prices). Settings are frozen on first start
  refreeze     accept changed settings for the paper run (needs --reason)
  status       show how the paper run is doing
  kill         emergency stop: block new buys and close any open position
  resume       clear the emergency stop / drawdown halt
  dashboard    open the visual dashboard (browser)
"""
import argparse
import subprocess
import sys

from . import log
from .config import DEFAULT_PROFILE, PROFILES, ROOT, load_config, starting_balance_usdt
from .data.bybit import BybitPublic
from .data.sync import quality_report, repair_gaps, sync_history
from .db import Database
from .models import now_ms


def cmd_sync(cfg, a):
    db = Database(cfg.data.db_path)
    client = BybitPublic(cfg.data.rest_url, cfg.category, cfg.symbol)
    for iv in (cfg.data.entry_interval, cfg.data.trend_interval):
        sync_history(client, db, cfg.symbol, iv, a.days)
        repair_gaps(client, db, cfg.symbol, iv)
        q = quality_report(db, cfg.symbol, iv)
        (log.ok if q["gaps"] == 0 else log.warn)(f"{iv}m data quality: {q['count']} candles, {q['gaps']} gaps")
    log.ok("Sync finished")


def _load_history(cfg, db):
    """Candles + indicator table for a backtest, or None if there is not enough data."""
    from .features import build_features
    entry = db.load_candles(cfg.symbol, cfg.data.entry_interval)
    trend = db.load_candles(cfg.symbol, cfg.data.trend_interval)
    if len(entry) < 1000:
        log.error(f"Only {len(entry)} 15m candles stored; run 'sync --days 365' first")
        return None
    feats = build_features(entry, trend, cfg.strategy, cfg.data.entry_interval, cfg.data.trend_interval)
    return entry, trend, feats


def cmd_backtest(cfg, a):
    from .backtest import run_backtest, split_ranges, with_overrides
    from .research import dataset_info, record_experiment
    from .strategies import TrendMomentum
    db = Database(cfg.data.db_path)
    hist = _load_history(cfg, db)
    if not hist:
        return
    entry, trend, feats = hist
    start, version = starting_balance_usdt(cfg), TrendMomentum(cfg.strategy).version
    ranges = split_ranges(len(entry), cfg)
    dev_hi = ranges["validation"][1]           # everything BEFORE the locked final test
    batch = now_ms()
    ds = dataset_info(entry[:dev_hi])
    log.ok(f"Backtest on {dev_hi} candles ({dev_hi / 96:.0f} days) before the locked final test, start {start:.2f} USDT")
    log.note(f"Final test period ({len(entry) - dev_hi} candles, the newest data) is LOCKED. Use 'final-check' once at the very end.")

    def save(kind, label, r, trades=True):
        record_experiment(db, kind=kind, label=label, cfg=cfg, strategy_version=version, dataset=ds,
                          result=r, batch=batch, include_trades=trades)

    for name in ("train", "validation"):
        lo, hi = ranges[name]
        r = run_backtest(entry, trend, cfg, start, lo, hi, name, feats)
        save("backtest", name, r)
        for line in r.summary_lines():
            log.note(line)
    log.note("--- Stress test: what if trading costs are higher? (train + validation) ---")
    for mult in (1.0, 2.0, 3.0):
        r = run_backtest(entry, trend, with_overrides(cfg, cost_mult=mult), start, 0, dev_hi, f"costs x{mult:g}", feats)
        save("stress", f"costs x{mult:g}", r, trades=False)
        log.note(f"costs x{mult:g}: result {r.net_return:+.2%}, {len(r.trades)} trades, max drop {r.max_drawdown:.2%}")
        if mult == 1.0 and r.blocked:
            log.note("  Most common blocks: " + ", ".join(f"{k} ({v})" for k, v in
                                                          sorted(r.blocked.items(), key=lambda x: -x[1])[:3]))
    log.note("--- Sensitivity: do small setting changes flip the result? (train + validation) ---")
    from .features import build_features
    s = cfg.strategy
    variants = {
        "RSI floor -5": {"rsi_min": s.rsi_min - 5}, "RSI floor +5": {"rsi_min": s.rsi_min + 5},
        "stop 1.5x ATR": {"stop_atr_mult": 1.5}, "stop 2.5x ATR": {"stop_atr_mult": 2.5},
        "target 2x ATR": {"target_atr_mult": 2.0}, "target 4x ATR": {"target_atr_mult": 4.0},
    }
    for name, ov in variants.items():
        c2 = with_overrides(cfg, strategy=ov)
        f2 = build_features(entry, trend, c2.strategy, cfg.data.entry_interval, cfg.data.trend_interval)
        r = run_backtest(entry, trend, c2, start, 0, dev_hi, name, f2)
        save("sensitivity", name, r, trades=False)
        log.note(f"{name}: result {r.net_return:+.2%}, {len(r.trades)} trades")
    log.ok("Backtest saved to the experiment log (see 'experiments'). Past results do not promise future results.")


def cmd_final_check(cfg, a):
    from .backtest import run_backtest, split_ranges
    from .research import check_final_test, dataset_info, record_experiment
    from .strategies import TrendMomentum
    db = Database(cfg.data.db_path)
    hist = _load_history(cfg, db)
    if not hist:
        return
    entry, trend, feats = hist
    lo, hi = split_ranges(len(entry), cfg)["test"]
    check = check_final_test(db, cfg, entry[lo].start, entry[hi - 1].start)   # raises if not allowed
    log.warn(f"FINAL TEST: {hi - lo} candles ({(hi - lo) / 96:.0f} days). Look at this once; do not tweak settings afterwards.")
    if check["prior_looks"]:
        log.warn(f"These dates were already used {check['prior_looks']} time(s) for other settings, so this result is less trustworthy.")
    if not a.confirm:
        log.note("Nothing was run. To take the final test, run: final-check --confirm")
        return
    r = run_backtest(entry, trend, cfg, starting_balance_usdt(cfg), lo, hi, "final test", feats)
    record_experiment(db, kind="final_test", label="final test", cfg=cfg,
                      strategy_version=TrendMomentum(cfg.strategy).version, dataset=dataset_info(entry[lo:hi]),
                      result=r, batch=now_ms(), note=f"prior_looks={check['prior_looks']}")
    for line in r.summary_lines():
        log.note(line)
    log.ok("Final test taken and saved. It is now used up for these settings.")


def cmd_experiments(cfg, a):
    import json
    from .research import recent_experiments
    rows = recent_experiments(Database(cfg.data.db_path), a.limit)
    if not rows:
        log.note("No experiments saved yet. Run 'backtest' first.")
        return
    for r in rows:
        m = json.loads(r["metrics_json"])
        when = __import__("datetime").datetime.fromtimestamp(r["ts_ms"] / 1000).strftime("%Y-%m-%d %H:%M")
        dirty = "+uncommitted" if r["git_dirty"] else ""
        log.note(f"#{r['id']} {when} {r['kind']}/{r['label']}: {m['net_return']:+.2%}, {m['trades']} trades, "
                 f"expectancy {m['expectancy']:+.4f} | {r['strategy_version']} cfg {r['config_hash'][:8]} "
                 f"code {r['git_commit']}{dirty}")


def cmd_run(cfg, a):
    from .runner import Runner
    Runner(cfg, heartbeat_seconds=a.heartbeat).run(minutes=a.minutes)


def cmd_refreeze(cfg, a):
    from .research import freeze_config
    rec = freeze_config(Database(cfg.data.db_path), cfg, reason=a.reason)
    log.warn("Paper settings re-frozen. Results before and after this point used different settings; treat it as a new experiment.")
    log.ok(f"New frozen settings id: {rec['hash']} (reason: {a.reason})")


def cmd_status(cfg, a):
    from .report import print_report, paper_report
    db = Database(cfg.data.db_path)
    print_report(paper_report(db, starting_balance_usdt(cfg)), log.note)
    frozen = db.get_state("frozen_config")
    log.note(f"Frozen settings id: {frozen['hash'] if frozen else 'not frozen yet (freezes on first run)'}")
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
    f = sub.add_parser("final-check")
    f.add_argument("--confirm", action="store_true", help="really take the final test (it can only be used once)")
    f.set_defaults(fn=cmd_final_check)
    e = sub.add_parser("experiments"); e.add_argument("--limit", type=int, default=15); e.set_defaults(fn=cmd_experiments)
    r = sub.add_parser("run")
    r.add_argument("--minutes", type=float, default=None, help="stop after N minutes (default: run until Ctrl+C)")
    r.add_argument("--heartbeat", type=int, default=60, help="seconds between status lines")
    r.set_defaults(fn=cmd_run)
    rf = sub.add_parser("refreeze")
    rf.add_argument("--reason", required=True, help="why the paper settings are being changed")
    rf.set_defaults(fn=cmd_refreeze)
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
