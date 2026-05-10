from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from scripts import quizbank_reports as reports
from tests.scripts.quizbank_reports_support import configure_paths, write_csv, write_report_set


def test_check_reports_notices_stale_mtimes_but_validates_content(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = configure_paths(monkeypatch, tmp_path)
    write_report_set(paths["reports_dir"])
    write_csv(paths["quizbank_dir"] / "bank.csv")
    for path in reports.REPORT_PATHS:
        os.utime(path, (100, 100))
    os.utime(paths["quizbank_dir"] / "bank.csv", (200, 200))

    def fake_refresh(output_dir: Path) -> None:
        write_report_set(output_dir)

    monkeypatch.setattr(reports, "_run_refresh", fake_refresh)

    assert reports.check_reports() == 0

    output = capsys.readouterr().out
    assert "Notice: some QuizBank reports are older than CSV files by mtime:" in output
    assert "QuizBank reports are up-to-date." in output


def test_main_refresh_dispatches_without_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []
    monkeypatch.setattr(sys, "argv", ["quizbank_reports.py", "refresh"])
    monkeypatch.setattr(reports, "refresh_reports", lambda: called.append("refresh"))

    reports.main()

    assert called == ["refresh"]


def test_main_check_exits_with_check_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["quizbank_reports.py", "check"])
    monkeypatch.setattr(reports, "check_reports", lambda: 7)

    with pytest.raises(SystemExit) as exc_info:
        reports.main()

    assert exc_info.value.code == 7
