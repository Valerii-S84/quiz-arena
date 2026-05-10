from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import quizbank_reports as reports


def configure_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    root = tmp_path
    quizbank_dir = root / "QuizBank"
    reports_dir = root / "reports"
    paths = {
        "inventory_json": reports_dir / "quizbank_inventory_audit.json",
        "inventory_md": reports_dir / "quizbank_inventory_audit.md",
        "audit_json": reports_dir / "quizbank_audit_report.json",
        "audit_md": reports_dir / "quizbank_audit_report.md",
        "ambiguity_json": reports_dir / "quizbank_ambiguity_scan.json",
        "ambiguity_md": reports_dir / "quizbank_ambiguity_scan.md",
        "quizbank_dir": quizbank_dir,
        "reports_dir": reports_dir,
    }
    monkeypatch.setattr(reports, "ROOT", root)
    monkeypatch.setattr(reports, "QUIZBANK_DIR", quizbank_dir)
    monkeypatch.setattr(reports, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(reports, "INVENTORY_JSON", paths["inventory_json"])
    monkeypatch.setattr(reports, "INVENTORY_MD", paths["inventory_md"])
    monkeypatch.setattr(reports, "AUDIT_JSON", paths["audit_json"])
    monkeypatch.setattr(reports, "AUDIT_MD", paths["audit_md"])
    monkeypatch.setattr(reports, "AMBIGUITY_JSON", paths["ambiguity_json"])
    monkeypatch.setattr(reports, "AMBIGUITY_MD", paths["ambiguity_md"])
    monkeypatch.setattr(
        reports,
        "REPORT_PATHS",
        [
            paths["inventory_json"],
            paths["inventory_md"],
            paths["audit_json"],
            paths["audit_md"],
            paths["ambiguity_json"],
            paths["ambiguity_md"],
        ],
    )
    return paths


def write_report_set(directory: Path, *, value: int = 1, md_suffix: str = "ok") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": "2026-05-10T12:00:00+00:00",
        "summary": {"generated_at_utc": "2026-05-10T12:00:00+00:00", "value": value},
    }
    markdown = f"# Report\nGenerated: `2026-05-10T12:00:00+00:00`\n{md_suffix}\n"
    for name in (
        "quizbank_inventory_audit.json",
        "quizbank_audit_report.json",
        "quizbank_ambiguity_scan.json",
    ):
        (directory / name).write_text(json.dumps(payload), encoding="utf-8")
    for name in (
        "quizbank_inventory_audit.md",
        "quizbank_audit_report.md",
        "quizbank_ambiguity_scan.md",
    ):
        (directory / name).write_text(markdown, encoding="utf-8")


def write_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("quiz_id,question\nq1,Frage?\n", encoding="utf-8")
