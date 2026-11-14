"""One readable diagnostic file: everything needed to judge the paper run, in plain text.
Used by the dashboard's download button and by `python -m trading_bot export-report`.
Read-only: it only reads the journal and the log files."""
import json
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT, starting_balance_usdt
from .diagnose import diagnose_trades, print_diagnosis
from .ops import ops_flags, ops_report, print_ops
from .report import paper_report, paper_trades, print_report, verdict

LOG_TAIL_LINES = 300


def tail_log(log_dir: Path | None = None, lines: int = LOG_TAIL_LINES) -> list[str]:
    """Last `lines` lines of logs/bot.log, reaching into the rotated backups if needed."""
    base = (log_dir or ROOT / "logs") / "bot.log"
    files = [base] + [base.with_name(f"bot.log.{i}") for i in range(1, 6)]  # newest first
    out: list[str] = []
    for f in files:
        if not f.exists():
            continue
        out = f.read_text(encoding="utf-8", errors="replace").splitlines() + out
        if len(out) >= lines:
            break
    return out[-lines:]


def _rows(db, sql: str) -> list[str]:
    return [" | ".join("" if v is None else str(v) for v in dict(r).values()) for r in db.conn.execute(sql)]


def section(title: str, body: list[str]) -> list[str]:
    return ["", "=" * 70, title, "=" * 70, *(body or ["(nothing yet)"])]


def command_outputs(db, cfg) -> dict[str, list[str]]:
    """What `status`, `ops` and `diagnose-paper` would print, as plain lines."""
    c = cfg.costs
    round_trip = 2 * (c.taker_fee + c.half_spread + c.slippage)
    start = starting_balance_usdt(cfg)

    status: list[str] = []
    r = paper_report(db, start)
    print_report(r, status.append)
    frozen = db.get_state("frozen_config")
    status.append(f"Frozen settings id: {frozen['hash'] if frozen else 'not frozen yet'}")
    status.append(f"Emergency stop: {'ON' if db.get_state('kill_switch', False) else 'off'}")
    risk = db.get_state("risk") or {}
    if risk.get("halted"):
        status.append(f"HALTED: {risk['halted']}")
    status.append("Verdict: " + verdict(r))

    ops: list[str] = []
    o = ops_report(db, cfg)
    print_ops(o, ops.append)

    diag: list[str] = []
    trades = paper_trades(db, cfg.symbol, cfg.data.entry_interval)
    diag.append(f"Facts from {len(trades)} closed trades (a round trip costs about {round_trip:.2%} of price).")
    print_diagnosis("paper", diagnose_trades(trades, round_trip), diag.append)
    return {"status": status, "ops": ops, "diagnose-paper": diag, "flags": ops_flags(o)}


def build_report(db, cfg, log_dir: Path | None = None) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    out = [f"PAPER RUN DIAGNOSTIC REPORT - created {now}",
           "Pretend money, real prices. Nothing in this file can place an order.",
           f"Symbol: {cfg.symbol} | decisions every {cfg.data.entry_interval}m | trend check {cfg.data.trend_interval}m"]
    cmds = command_outputs(db, cfg)

    out += section("1. NEEDS A LOOK (health flags)", cmds["flags"] or ["Nothing odd in the bot's health."])
    out += section("2. STATUS (same as `status`)", cmds["status"])
    out += section("3. BOT HEALTH (same as `ops`)", cmds["ops"])
    out += section("4. WHY WINNING OR LOSING (same as `diagnose-paper`)", cmds["diagnose-paper"])

    frozen = db.get_state("frozen_config")
    out += section("5. FROZEN SETTINGS (used for the whole run)",
                   [json.dumps(frozen, indent=2, default=str)] if frozen else [])
    out += section("6. OPEN POSITION", [json.dumps(db.get_state("position"), default=str)]
                   if db.get_state("position") else ["None"])
    out += section("7. WARNINGS AND ERRORS (newest first, last 100)",
                   _rows(db, "SELECT datetime(ts_ms/1000,'unixepoch') AS time, level, kind, message FROM events "
                             "WHERE level IN ('WARN','ERROR') ORDER BY id DESC LIMIT 100"))
    out += section("8. TRADES (newest first, last 200)",
                   _rows(db, "SELECT datetime(ts_ms/1000,'unixepoch') AS time, side, qty, price, fee, realized_gross, "
                             "realized_net, reason FROM fills ORDER BY id DESC LIMIT 200"))
    out += section("9. DECISIONS (newest first, last 200)",
                   _rows(db, "SELECT datetime(ts_ms/1000,'unixepoch') AS time, kind, action, reasons FROM decisions "
                             "ORDER BY id DESC LIMIT 200"))
    out += section(f"10. BOT LOG (last {LOG_TAIL_LINES} lines, times are UTC)", tail_log(log_dir))
    return "\n".join(out) + "\n"


def write_report(db, cfg, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or ROOT / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"diagnostic-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.txt"
    path.write_text(build_report(db, cfg), encoding="utf-8")
    return path
