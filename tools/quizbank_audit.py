#!/usr/bin/env python3
"""Run structural and quality audits for quiz bank tables."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from quizbank_audit_analysis import audit_table
from quizbank_audit_io import read_table
from quizbank_audit_report import build_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit quiz bank files.")
    parser.add_argument("--input-dir", default="QuizBank", help="Directory with quiz files.")
    parser.add_argument(
        "--output-json",
        default="reports/quizbank_audit_report.json",
        help="Path to JSON report file.",
    )
    parser.add_argument(
        "--output-md",
        default="reports/quizbank_audit_report.md",
        help="Path to Markdown report file.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    files = sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".csv", ".xlsx", ".xlsm"}
    )

    file_reports = []
    for file_path in files:
        table = read_table(file_path)
        file_reports.append(audit_table(file_path, table))

    summary = {
        "file_count": len(file_reports),
        "row_count": sum(item["row_count"] for item in file_reports),
        "ready_count": sum(1 for item in file_reports if item["readiness"] == "ready"),
        "ready_with_cleanup_count": sum(
            1 for item in file_reports if item["readiness"] == "ready_with_cleanup"
        ),
        "needs_fix_count": sum(1 for item in file_reports if item["readiness"] == "needs_fix"),
        "critical_total": sum(item["severity"]["critical"] for item in file_reports),
        "high_total": sum(item["severity"]["high"] for item in file_reports),
        "medium_total": sum(item["severity"]["medium"] for item in file_reports),
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(input_dir),
        "summary": summary,
        "files": file_reports,
    }

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(build_markdown(report), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"JSON report: {output_json}")
    print(f"Markdown report: {output_md}")


if __name__ == "__main__":
    main()
