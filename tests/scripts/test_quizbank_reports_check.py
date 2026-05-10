from __future__ import annotations

from pathlib import Path

import pytest

from scripts import quizbank_reports as reports
from tests.scripts.quizbank_reports_support import configure_paths, write_csv, write_report_set


def test_check_reports_reports_missing_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_paths(monkeypatch, tmp_path)

    assert reports.check_reports() == 1

    output = capsys.readouterr().out
    assert "Missing QuizBank reports:" in output
    assert "Run: python scripts/quizbank_reports.py refresh" in output


def test_check_reports_requires_csv_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = configure_paths(monkeypatch, tmp_path)
    write_report_set(paths["reports_dir"])

    assert reports.check_reports() == 1

    assert capsys.readouterr().out == "No QuizBank CSV files found.\n"


def test_check_reports_accepts_matching_generated_reports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = configure_paths(monkeypatch, tmp_path)
    write_csv(paths["quizbank_dir"] / "bank.csv")
    write_report_set(paths["reports_dir"])

    def fake_refresh(output_dir: Path) -> None:
        write_report_set(output_dir)

    monkeypatch.setattr(reports, "_run_refresh", fake_refresh)

    assert reports.check_reports() == 0

    assert "QuizBank reports are up-to-date." in capsys.readouterr().out


def test_check_reports_reports_json_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = configure_paths(monkeypatch, tmp_path)
    write_csv(paths["quizbank_dir"] / "bank.csv")
    write_report_set(paths["reports_dir"], value=1)

    def fake_refresh(output_dir: Path) -> None:
        write_report_set(output_dir, value=2)

    monkeypatch.setattr(reports, "_run_refresh", fake_refresh)

    assert reports.check_reports() == 1

    output = capsys.readouterr().out
    assert "QuizBank report mismatch: reports/quizbank_inventory_audit.json" in output
    assert "Run: python scripts/quizbank_reports.py refresh" in output


def test_check_reports_reports_markdown_mismatch_with_diff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = configure_paths(monkeypatch, tmp_path)
    write_csv(paths["quizbank_dir"] / "bank.csv")
    write_report_set(paths["reports_dir"], md_suffix="repo")

    def fake_refresh(output_dir: Path) -> None:
        write_report_set(output_dir, md_suffix="expected")

    monkeypatch.setattr(reports, "_run_refresh", fake_refresh)

    assert reports.check_reports() == 1

    output = capsys.readouterr().out
    assert "QuizBank report mismatch: reports/quizbank_inventory_audit.md" in output
    assert "--- reports/quizbank_inventory_audit.md (repo)" in output
