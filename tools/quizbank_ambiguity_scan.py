#!/usr/bin/env python3
"""Focused scan for duplicates/repeats and potential multi-correct ambiguity."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from quizbank_ambiguity_constants import CUE_PREFIXES, OPTION_COLUMNS
from quizbank_ambiguity_io import read_csv, read_table, read_xlsx
from quizbank_ambiguity_report import build_md
from quizbank_ambiguity_scan_core import scan_file
from quizbank_ambiguity_text import key_family, norm, question_signature

__all__ = [
    "CUE_PREFIXES",
    "OPTION_COLUMNS",
    "norm",
    "question_signature",
    "key_family",
    "read_csv",
    "read_xlsx",
    "read_table",
    "scan_file",
    "build_md",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan quiz bank for duplicates and ambiguity.")
    parser.add_argument("--input-dir", default="QuizBank")
    parser.add_argument("--output-json", default="reports/quizbank_ambiguity_scan.json")
    parser.add_argument("--output-md", default="reports/quizbank_ambiguity_scan.md")
    args = parser.parse_args()

    files = sorted(
        [
            p
            for p in Path(args.input_dir).iterdir()
            if p.is_file() and p.suffix.lower() in {".csv", ".xlsx", ".xlsm"}
        ]
    )
    results = [scan_file(p) for p in files]
    summary = {
        "file_count": len(results),
        "exact_duplicate_groups_total": sum(len(r["exact_duplicate_groups"]) for r in results),
        "exact_conflict_groups_total": sum(len(r["exact_conflict_groups"]) for r in results),
        "signature_conflict_groups_total": sum(
            len(r["signature_conflict_groups"]) for r in results
        ),
        "fuzzy_conflicts_total": sum(len(r["fuzzy_conflicts"]) for r in results),
        "same_row_candidates_total": sum(
            len(r["same_row_multi_logical_candidates"]) for r in results
        ),
        "template_repeat_groups_total": sum(len(r["template_repeat_groups"]) for r in results),
        "template_repeat_rows_total": sum(
            sum(group["size"] for group in r["template_repeat_groups"]) for r in results
        ),
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "files": results,
    }

    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(build_md(report), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"JSON: {out_json}")
    print(f"MD: {out_md}")


if __name__ == "__main__":
    main()
