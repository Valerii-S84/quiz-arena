#!/usr/bin/env python3
"""Refresh and validate QuizBank reports."""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
QUIZBANK_DIR = ROOT / "QuizBank"
REPORTS_DIR = ROOT / "reports"

INVENTORY_JSON = REPORTS_DIR / "quizbank_inventory_audit.json"
INVENTORY_MD = REPORTS_DIR / "quizbank_inventory_audit.md"
AUDIT_JSON = REPORTS_DIR / "quizbank_audit_report.json"
AUDIT_MD = REPORTS_DIR / "quizbank_audit_report.md"
AMBIGUITY_JSON = REPORTS_DIR / "quizbank_ambiguity_scan.json"
AMBIGUITY_MD = REPORTS_DIR / "quizbank_ambiguity_scan.md"

REPORT_PATHS = [
    INVENTORY_JSON,
    INVENTORY_MD,
    AUDIT_JSON,
    AUDIT_MD,
    AMBIGUITY_JSON,
    AMBIGUITY_MD,
]


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, cwd=ROOT)


def _run_refresh(output_dir: Path) -> None:
    _run(
        [
            sys.executable,
            "tools/quizbank_inventory_audit.py",
            "--input-dir",
            "QuizBank",
            "--output-json",
            str(output_dir / "quizbank_inventory_audit.json"),
            "--output-md",
            str(output_dir / "quizbank_inventory_audit.md"),
        ]
    )
    _run(
        [
            sys.executable,
            "tools/quizbank_audit.py",
            "--input-dir",
            "QuizBank",
            "--output-json",
            str(output_dir / "quizbank_audit_report.json"),
            "--output-md",
            str(output_dir / "quizbank_audit_report.md"),
        ]
    )
    _run(
        [
            sys.executable,
            "tools/quizbank_ambiguity_scan.py",
            "--input-dir",
            "QuizBank",
            "--output-json",
            str(output_dir / "quizbank_ambiguity_scan.json"),
            "--output-md",
            str(output_dir / "quizbank_ambiguity_scan.md"),
        ]
    )


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_json(data: dict[str, Any]) -> dict[str, Any]:
    cloned = json.loads(json.dumps(data))
    cloned.pop("generated_at", None)
    if isinstance(cloned.get("summary"), dict):
        cloned["summary"].pop("generated_at_utc", None)
    return cloned


def _normalize_md(content: str) -> str:
    normalized = re.sub(r"`\d{4}-\d{2}-\d{2}T[^`]+`", "`<generated_at>`", content)
    return normalized.rstrip() + "\n"


def _diff_preview(expected: str, actual: str, rel_name: str) -> str:
    lines = list(
        difflib.unified_diff(
            actual.splitlines(),
            expected.splitlines(),
            fromfile=f"{rel_name} (repo)",
            tofile=f"{rel_name} (expected)",
            lineterm="",
        )
    )
    return "\n".join(lines[:80])


def refresh_reports() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _run_refresh(REPORTS_DIR)
    print("QuizBank reports refreshed.")


def check_reports() -> int:
    missing = [path for path in REPORT_PATHS if not path.exists()]
    if missing:
        print("Missing QuizBank reports:")
        for path in missing:
            print(f"- {path.relative_to(ROOT)}")
        print("Run: python scripts/quizbank_reports.py refresh")
        return 1

    csv_files = sorted(QUIZBANK_DIR.glob("*.csv"))
    if not csv_files:
        print("No QuizBank CSV files found.")
        return 1

    latest_csv_mtime = max(path.stat().st_mtime for path in csv_files)
    stale_paths = [path for path in REPORT_PATHS if path.stat().st_mtime < latest_csv_mtime]
    if stale_paths:
        print("Notice: some QuizBank reports are older than CSV files by mtime:")
        for path in stale_paths:
            print(f"- {path.relative_to(ROOT)}")
        print("Proceeding with content-based freshness validation.")

    with tempfile.TemporaryDirectory(prefix="quizbank_reports_check_") as temp_dir:
        temp_path = Path(temp_dir)
        _run_refresh(temp_path)

        json_pairs = [
            ("reports/quizbank_inventory_audit.json", INVENTORY_JSON, temp_path / INVENTORY_JSON.name),
            ("reports/quizbank_audit_report.json", AUDIT_JSON, temp_path / AUDIT_JSON.name),
            ("reports/quizbank_ambiguity_scan.json", AMBIGUITY_JSON, temp_path / AMBIGUITY_JSON.name),
        ]
        for rel_name, actual_path, expected_path in json_pairs:
            actual = _normalize_json(_load_json(actual_path))
            expected = _normalize_json(_load_json(expected_path))
            if actual != expected:
                print(f"QuizBank report mismatch: {rel_name}")
                print("Run: python scripts/quizbank_reports.py refresh")
                return 1

        md_pairs = [
            ("reports/quizbank_inventory_audit.md", INVENTORY_MD, temp_path / INVENTORY_MD.name),
            ("reports/quizbank_audit_report.md", AUDIT_MD, temp_path / AUDIT_MD.name),
            ("reports/quizbank_ambiguity_scan.md", AMBIGUITY_MD, temp_path / AMBIGUITY_MD.name),
        ]
        for rel_name, actual_path, expected_path in md_pairs:
            actual_md = _normalize_md(actual_path.read_text(encoding="utf-8"))
            expected_md = _normalize_md(expected_path.read_text(encoding="utf-8"))
            if actual_md != expected_md:
                print(f"QuizBank report mismatch: {rel_name}")
                print(_diff_preview(expected_md, actual_md, rel_name))
                print("Run: python scripts/quizbank_reports.py refresh")
                return 1

    print("QuizBank reports are up-to-date.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh/check QuizBank reports.")
    parser.add_argument("command", choices=["refresh", "check"])
    args = parser.parse_args()

    if args.command == "refresh":
        refresh_reports()
        return

    raise SystemExit(check_reports())


if __name__ == "__main__":
    main()
