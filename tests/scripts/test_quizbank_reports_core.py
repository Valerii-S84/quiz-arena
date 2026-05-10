from __future__ import annotations

from pathlib import Path

import pytest

from scripts import quizbank_reports as reports
from tests.scripts.quizbank_reports_support import configure_paths


def test_run_delegates_to_subprocess_with_repo_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], bool, Path]] = []

    def fake_run(cmd: list[str], *, check: bool, cwd: Path) -> None:
        calls.append((cmd, check, cwd))

    monkeypatch.setattr(reports.subprocess, "run", fake_run)

    reports._run(["python", "--version"])

    assert calls == [(["python", "--version"], True, reports.ROOT)]


def test_run_refresh_invokes_all_report_generators(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(reports, "_run", commands.append)

    reports._run_refresh(tmp_path)

    assert [Path(command[1]).name for command in commands] == [
        "quizbank_inventory_audit.py",
        "quizbank_audit.py",
        "quizbank_ambiguity_scan.py",
    ]
    assert all(str(tmp_path) in " ".join(command) for command in commands)


def test_normalizers_ignore_generated_timestamps() -> None:
    assert reports._normalize_json(
        {"generated_at": "x", "summary": {"generated_at_utc": "y", "value": 1}}
    ) == {"summary": {"value": 1}}
    assert reports._normalize_md("Generated: `2026-05-10T12:00:00+00:00`\n") == (
        "Generated: `<generated_at>`\n"
    )


def test_diff_preview_is_limited() -> None:
    preview = reports._diff_preview("a\nb\n", "a\nc\n", "reports/example.md")

    assert "--- reports/example.md (repo)" in preview
    assert "+++ reports/example.md (expected)" in preview


def test_refresh_reports_creates_directory_and_runs_refresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = configure_paths(monkeypatch, tmp_path)
    refreshed: list[Path] = []
    monkeypatch.setattr(reports, "_run_refresh", refreshed.append)

    reports.refresh_reports()

    assert refreshed == [paths["reports_dir"]]
    assert paths["reports_dir"].is_dir()
    assert capsys.readouterr().out == "QuizBank reports refreshed.\n"
