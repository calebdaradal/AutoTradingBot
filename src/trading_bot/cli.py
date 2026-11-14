"""Command-line entry point:  python -m trading_bot <command>

  sync         download recent price history and check it for gaps
  backtest     replay the strategy on past data (train + validation + stress tests). The final test is LOCKED
                 --candidate <version> tests a new idea (needs a written hypothesis first)
  diagnose     facts about why the v1.0 baseline loses (reads its saved backtests)
  diagnose-paper  the same facts, but for the real paper-trading run (reads its closed trades)
  hypothesis   add / list / close ideas. One at a time, written down before testing
  final-check  take the locked final test (needs --candidate and --confirm; only for a qualified candidate)
  experiments  list the saved receipts of past backtests
  invalidate   flag a broken TEST (bug, bad data, crashed run) so it is not counted as evidence; reopens the idea
  run          start paper trading (fake money, real prices). Settings are frozen on first start
  refreeze     accept changed settings for the paper run (needs --reason)
  status       show how the paper run is doing
  ops          health check of the paper run itself (feed, orders, missed candles, fill costs)
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
    from . import hypotheses as hy
    from .candidates import build_candidate
    from .strategies import TrendMomentum
    db = Database(cfg.data.db_path)
    strat, hyp = None, None
    if a.candidate:                                  # a new idea: must be written down first, and still untested
        hyp = hy.open_hypothesis(db)
        if not hyp or hyp["candidate"] != a.candidate or hyp["state"] != "DRAFT":
            raise hy.HypothesisError(f"No untested hypothesis exists for {a.candidate}. "
                                     f"Write it first with 'hypothesis add' (one idea at a time).")
        strat = build_candidate(a.candidate, cfg.strategy)
        log.note(f"Testing candidate {strat.version} for hypothesis {hyp['id']}: {hyp['title']}")
    hist = _load_history(cfg, db)
    if not hist:
        return
    entry, trend, feats = hist
    start, version = starting_balance_usdt(cfg), (strat or TrendMomentum(cfg.strategy)).version
    ranges = split_ranges(len(entry), cfg)
    dev_hi = ranges["validation"][1]           # everything BEFORE the locked final test
    from .models import interval_ms
    from .research import invalidate_experiments, validate_candles
    problems = (validate_candles(entry[:dev_hi], interval_ms(cfg.data.entry_interval))
                + validate_candles(trend, interval_ms(cfg.data.trend_interval)))
    if problems:                                # broken data = broken test. Nothing is run or judged.
        for p in problems:
            log.error(f"Data problem: {p}")
        log.error("Backtest NOT run: this is a data fault, not a strategy result. "
                  "Run 'sync' to repair, then try again. The hypothesis stays untested.")
        return
    batch = now_ms()
    ds = dataset_info(entry[:dev_hi])
    log.ok(f"Backtest on {dev_hi} candles ({dev_hi / 96:.0f} days) before the locked final test, start {start:.2f} USDT")
    log.note(f"Final test period ({len(entry) - dev_hi} candles, the newest data) is LOCKED. Use 'final-check' once at the very end.")
    saved = []

    def save(kind, label, r, trades=True):
        saved.append(record_experiment(db, kind=kind, label=label, cfg=cfg, strategy_version=version, dataset=ds,
                                       result=r, batch=batch, include_trades=trades,
                                       note=f"hypothesis={hyp['id']}" if hyp else ""))

    dev = {}
    try:
        for name in ("train", "validation"):
            lo, hi = ranges[name]
            r = run_backtest(entry, trend, cfg, start, lo, hi, name, feats, strat=strat)
            dev[name] = r.metrics()
            save("backtest", name, r)
            for line in r.summary_lines():
                log.note(line)
        log.note("--- Stress test: what if trading costs are higher? (train + validation) ---")
        for mult in (1.0, 2.0, 3.0):
            r = run_backtest(entry, trend, with_overrides(cfg, cost_mult=mult), start, 0, dev_hi, f"costs x{mult:g}",
                             feats, strat=strat)
            save("stress", f"costs x{mult:g}", r, trades=False)
            log.note(f"costs x{mult:g}: result {r.net_return:+.2%}, {len(r.trades)} trades, max drop {r.max_drawdown:.2%}")
            if mult == 1.0 and r.blocked:
                log.note("  Most common blocks: " + ", ".join(f"{k} ({v})" for k, v in
                                                              sorted(r.blocked.items(), key=lambda x: -x[1])[:3]))
    except Exception as e:                      # a crashed run is a technical failure, never a strategy verdict
        log.error(f"Backtest crashed: {type(e).__name__}: {e}")
        if saved:
            invalidate_experiments(db, saved, "failed_run", f"run crashed: {type(e).__name__}: {e}")
            log.warn(f"{len(saved)} partial result(s) flagged INVALID (failed run). Fix the problem and run again.")
        log.warn("No verdict was recorded. This says nothing about whether the idea works.")
        return
    if hyp:
        done = hy.record_dev_results(db, hyp["id"], dev, batch)
        why = done["history"][-1]["reason"]
        (log.ok if done["state"] == "QUALIFIED_CANDIDATE" else log.warn)(f"{hyp['id']} is now {done['state']}: {why}")
        log.note("Candidates are not sensitivity-tested here; that is a later robustness step.")
        return
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
    from . import hypotheses as hy
    from .candidates import build_candidate
    from .research import check_final_test, dataset_info, record_experiment
    db = Database(cfg.data.db_path)
    hyp = hy.require_final_ready(db, a.candidate)      # raises unless a QUALIFIED_CANDIDATE is waiting (never v1.0)
    strat = build_candidate(a.candidate, cfg.strategy)
    hist = _load_history(cfg, db)
    if not hist:
        return
    entry, trend, feats = hist
    lo, hi = split_ranges(len(entry), cfg)["test"]
    check = check_final_test(db, cfg, entry[lo].start, entry[hi - 1].start, strat.version)   # raises if not allowed
    log.note(f"Candidate {strat.version} ({hyp['id']}: {hyp['title']}) passed train + validation. "
             f"Pass marks were fixed in advance: {hyp['thresholds']}")
    log.warn(f"FINAL TEST: {hi - lo} candles ({(hi - lo) / 96:.0f} days). Look at this once; do not tweak settings afterwards.")
    if check["prior_looks"]:
        log.warn(f"These dates were already used {check['prior_looks']} time(s) for other settings, so this result is less trustworthy.")
    if not a.confirm:
        log.note("Nothing was run. To take the final test, run: final-check --confirm")
        return
    r = run_backtest(entry, trend, cfg, starting_balance_usdt(cfg), lo, hi, "final test", feats, strat=strat)
    exp_id = record_experiment(db, kind="final_test", label="final test", cfg=cfg,
                               strategy_version=strat.version, dataset=dataset_info(entry[lo:hi]),
                               result=r, batch=now_ms(),
                               note=f"hypothesis={hyp['id']} prior_looks={check['prior_looks']}")
    for line in r.summary_lines():
        log.note(line)
    done = hy.record_final_result(db, hyp["id"], r.metrics(), exp_id)
    (log.ok if done["final"]["passed"] else log.warn)(f"Final test taken and saved. {hyp['id']} is now {done['state']}: "
                                                      f"{done['history'][-1]['reason']}")


def cmd_diagnose(cfg, a):
    from .diagnose import BASELINE_VERSION, diagnose_trades, load_trades, print_diagnosis
    version = a.version or BASELINE_VERSION
    c = cfg.costs
    round_trip = 2 * (c.taker_fee + c.half_spread + c.slippage)
    log.note(f"Why does {version} lose? Facts from its saved backtests (a round trip costs about {round_trip:.2%} of price).")
    trades = load_trades(Database(cfg.data.db_path), version)
    for label, t in trades.items():
        print_diagnosis(label, diagnose_trades(t, round_trip), log.note)
    log.ok("Diagnosis done. These are measurements, not explanations. Ideas go in 'hypothesis add'.")


def cmd_diagnose_paper(cfg, a):
    from .diagnose import diagnose_trades, print_diagnosis
    from .report import paper_trades
    c = cfg.costs
    round_trip = 2 * (c.taker_fee + c.half_spread + c.slippage)
    trades = paper_trades(Database(cfg.data.db_path), cfg.symbol, cfg.data.entry_interval)
    log.note(f"Why is the paper run winning or losing? Facts from its {len(trades)} closed trades "
             f"(a round trip costs about {round_trip:.2%} of price).")
    print_diagnosis("paper", diagnose_trades(trades, round_trip), log.note)
    log.ok("Paper diagnosis done. These are measurements, not explanations. Ideas go in 'hypothesis add'.")


def cmd_hypothesis(cfg, a):
    from . import hypotheses as hy
    db = Database(cfg.data.db_path)
    if a.action == "add":
        for need in ("title", "statement", "prediction", "candidate"):
            if not getattr(a, need):
                raise hy.HypothesisError(f"--{need} is required")
        h = hy.add_hypothesis(db, title=a.title, statement=a.statement, prediction=a.prediction,
                              candidate=a.candidate, min_profit_factor=a.min_pf, min_trades=a.min_trades,
                              min_return=a.min_return)
        log.ok(f"{h['id']} written down (DRAFT). Pass marks are now fixed: {h['thresholds']}. "
               f"Next: backtest --candidate {h['candidate']}")
    elif a.action == "close":
        if not a.id:
            raise hy.HypothesisError("--id is required")
        h = hy.close_hypothesis(db, a.id, a.reason)
        log.ok(f"{h['id']} closed as {h['state']}: {a.reason}")
    else:
        items = hy.list_hypotheses(db)
        for h in items:
            log.note(f"{h['id']} [{h['state']}] {h['title']} | candidate {h['candidate']}")
            log.note(f"   idea: {h['statement']}")
            log.note(f"   expected: {h['prediction']}")
            log.note(f"   last step: {h['history'][-1]['reason']}")
            if h.get("invalidations"):
                log.note(f"   broken tests so far: {len(h['invalidations'])} (flagged invalid, not counted as failures)")
        log.ok(f"{len(items)} hypothesis(es) on file" if items else "No hypotheses yet. Add one with 'hypothesis add'")


def cmd_experiments(cfg, a):
    import json
    from .research import recent_experiments
    rows = recent_experiments(Database(cfg.data.db_path), a.limit)
    if not rows:
        log.note("No experiments saved yet. Run 'backtest' first.")
        return
    from .research import invalid_experiments
    bad = invalid_experiments(Database(cfg.data.db_path))
    for r in rows:
        m = json.loads(r["metrics_json"])
        when = __import__("datetime").datetime.fromtimestamp(r["ts_ms"] / 1000).strftime("%Y-%m-%d %H:%M")
        dirty = "+uncommitted" if r["git_dirty"] else ""
        flag = f" [INVALID TEST: {bad[r['id']]['category']}, not evidence]" if r["id"] in bad else ""
        log.note(f"#{r['id']} (batch {r['batch']}) {when} {r['kind']}/{r['label']}: {m['net_return']:+.2%}, "
                 f"{m['trades']} trades, expectancy {m['expectancy']:+.4f} | {r['strategy_version']} "
                 f"cfg {r['config_hash'][:8]} code {r['git_commit']}{dirty}{flag}")


def cmd_invalidate(cfg, a):
    from . import hypotheses as hy
    out = hy.invalidate_batch(Database(cfg.data.db_path), a.batch, a.category, a.reason)
    log.ok(f"{len(out['experiment_ids'])} experiment(s) flagged INVALID ({a.category}): they are not evidence about the strategy")
    for hid in out["reopened"]:
        log.ok(f"{hid} verdict withdrawn and reopened (DRAFT). Fix the problem, then re-run 'backtest --candidate ...'")


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


def cmd_ops(cfg, a):
    from .ops import ops_report, print_ops
    print_ops(ops_report(Database(cfg.data.db_path), cfg), log.note)
    log.ok("Ops report done")


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
    b = sub.add_parser("backtest")
    b.add_argument("--candidate", default=None, help="test a new strategy version (needs an open hypothesis for it)")
    b.set_defaults(fn=cmd_backtest)
    f = sub.add_parser("final-check")
    f.add_argument("--candidate", required=True, help="strategy version to test; it must be a QUALIFIED_CANDIDATE")
    f.add_argument("--confirm", action="store_true", help="really take the final test (it can only be used once)")
    f.set_defaults(fn=cmd_final_check)
    h = sub.add_parser("hypothesis")
    h.add_argument("action", choices=["add", "list", "close"])
    h.add_argument("--id"); h.add_argument("--reason", default="")
    h.add_argument("--title"); h.add_argument("--statement"); h.add_argument("--prediction")
    h.add_argument("--candidate")
    h.add_argument("--min-pf", type=float, default=1.2, help="profit factor needed (1.0 = break-even)")
    h.add_argument("--min-trades", type=int, default=20, help="fewest trades per period to trust the result")
    h.add_argument("--min-return", type=float, default=0.0, help="return needed in each period (0.0 = above zero)")
    h.set_defaults(fn=cmd_hypothesis)
    e = sub.add_parser("experiments"); e.add_argument("--limit", type=int, default=15); e.set_defaults(fn=cmd_experiments)
    iv = sub.add_parser("invalidate")
    iv.add_argument("--batch", type=int, required=True, help="batch number shown by 'experiments'")
    iv.add_argument("--category", required=True, choices=["bug", "bad_data", "failed_run"],
                    help="what was technically wrong with the TEST (a bad result is not a reason)")
    iv.add_argument("--reason", required=True, help="what was wrong and what was fixed")
    iv.set_defaults(fn=cmd_invalidate)
    r = sub.add_parser("run")
    r.add_argument("--minutes", type=float, default=None, help="stop after N minutes (default: run until Ctrl+C)")
    r.add_argument("--heartbeat", type=int, default=60, help="seconds between status lines")
    r.set_defaults(fn=cmd_run)
    rf = sub.add_parser("refreeze")
    rf.add_argument("--reason", required=True, help="why the paper settings are being changed")
    rf.set_defaults(fn=cmd_refreeze)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("ops").set_defaults(fn=cmd_ops)
    d = sub.add_parser("diagnose"); d.add_argument("--version", default=None); d.set_defaults(fn=cmd_diagnose)
    sub.add_parser("diagnose-paper").set_defaults(fn=cmd_diagnose_paper)
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
