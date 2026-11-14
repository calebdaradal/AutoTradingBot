from trading_bot.export import build_report, tail_log, write_report


def test_tail_log_reads_rotated_files_in_order(tmp_path):
    (tmp_path / "bot.log.1").write_text("old1\nold2\n")
    (tmp_path / "bot.log").write_text("new1\nnew2\n")
    assert tail_log(tmp_path, lines=3) == ["old2", "new1", "new2"]


def test_tail_log_missing_dir_is_empty(tmp_path):
    assert tail_log(tmp_path / "nope") == []


def test_report_on_empty_journal_has_all_sections(db, cfg, tmp_path):
    (tmp_path / "bot.log").write_text("2026-11-15 00:00:00Z INFO hello\n")
    text = build_report(db, cfg, tmp_path)
    for head in ("NEEDS A LOOK", "STATUS", "BOT HEALTH", "WHY WINNING OR LOSING",
                 "FROZEN SETTINGS", "WARNINGS AND ERRORS", "TRADES", "DECISIONS", "BOT LOG"):
        assert head in text
    assert "hello" in text


def test_write_report_creates_file(db, cfg, tmp_path):
    path = write_report(db, cfg, tmp_path)
    assert path.exists() and path.read_text(encoding="utf-8").startswith("PAPER RUN DIAGNOSTIC REPORT")
