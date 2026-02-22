#!/usr/bin/env python3
"""Inventory audit for QuizBank CSV files."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _norm_level(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text


def scan_csv(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        has_level_column = "level" in fieldnames
        row_count = 0
        level_counts: Counter[str] = Counter()

        for row in reader:
            row_count += 1
            if has_level_column:
                level = _norm_level(row.get("level"))
                if level:
                    level_counts[level] += 1

    return {
        "file": path.name,
        "rows": row_count,
        "has_level_column": has_level_column,
        "levels": dict(sorted(level_counts.items())),
    }


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# QuizBank Inventory Audit",
        "",
        f"Generated (UTC): `{summary['generated_at_utc']}`",
        "",
        "## Summary",
        "",
        f"- Total CSV files: **{summary['total_csv_files']}**",
        f"- Files with `level` column: **{summary['files_with_level_column']}**",
        f"- Files without `level` column: **{summary['files_without_level_column']}**",
        f"- Total quiz rows: **{summary['total_rows']}**",
    ]

    levels_total = summary["levels_total"]
    if levels_total:
        level_summary = ", ".join(f"{level}: {count}" for level, count in levels_total.items())
        lines.append(f"- Total by levels: `{level_summary}`")
    else:
        lines.append("- Total by levels: `N/A`")

    lines.extend(
        [
            "",
            "## Per File",
            "",
            "| File | Rows | Levels |",
            "|---|---:|---|",
        ]
    )
    for item in report["per_file"]:
        levels = item["levels"]
        if levels:
            levels_text = ", ".join(f"{level}:{count}" for level, count in levels.items())
        else:
            levels_text = "N/A"
        lines.append(f"| `{item['file']}` | {item['rows']} | {levels_text} |")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate QuizBank inventory audit.")
    parser.add_argument("--input-dir", default="QuizBank", help="Directory with QuizBank CSV files.")
    parser.add_argument(
        "--output-json",
        default="reports/quizbank_inventory_audit.json",
        help="Path to JSON report file.",
    )
    parser.add_argument(
        "--output-md",
        default="reports/quizbank_inventory_audit.md",
        help="Path to Markdown report file.",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    files = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv")
    per_file = [scan_csv(path) for path in files]

    levels_total: Counter[str] = Counter()
    for item in per_file:
        levels_total.update(item["levels"])

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_dir": str(input_dir),
        "total_csv_files": len(per_file),
        "files_with_level_column": sum(1 for item in per_file if item["has_level_column"]),
        "files_without_level_column": sum(1 for item in per_file if not item["has_level_column"]),
        "total_rows": sum(item["rows"] for item in per_file),
        "levels_total": dict(sorted(levels_total.items())),
    }
    report = {"summary": summary, "per_file": per_file}

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
