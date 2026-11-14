"""Simple console + file logging.

Console shows one short line per event:
  ✔ something worked      • neutral note      ⚠ warning      ✘ error
The log file (logs/bot.log) keeps the same lines with timestamps.
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_TAGS = {"ok": "✔", "note": "•", "warn": "⚠", "error": "✘"}
_logger = logging.getLogger("trading_bot")
_configured = False


class _ConsoleFormat(logging.Formatter):
    def format(self, record):
        tag = _TAGS.get(getattr(record, "tag", "note"), "•")
        return f"{tag} {record.getMessage()}"


def setup(log_dir="logs"):
    """Call once at program start."""
    global _configured
    if _configured:
        return
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    _logger.setLevel(logging.DEBUG)
    _logger.propagate = False

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(_ConsoleFormat())
    _logger.addHandler(console)

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        Path(log_dir) / "bot.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)sZ %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    logging.Formatter.converter = __import__("time").gmtime  # log files use UTC
    _logger.addHandler(file_handler)
    _configured = True


def ok(msg):
    _logger.info(msg, extra={"tag": "ok"})


def note(msg):
    _logger.info(msg, extra={"tag": "note"})


def warn(msg):
    _logger.warning(msg, extra={"tag": "warn"})


def error(msg):
    _logger.error(msg, extra={"tag": "error"})
