"""Reporting utilities for quiz bank ambiguity scan."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_md(report: dict[str, Any]) -> str:
    lines = ["# QuizBank Duplicate & Ambiguity Scan", ""]
    lines.append(f"- Generated at: `{report['generated_at']}`")
    lines.append(f"- Files scanned: `{len(report['files'])}`")
    lines.append("")
    lines.append(
        "| File | Rows | Exact duplicate groups | Exact conflict groups | "
        "Signature conflict groups | Fuzzy conflicts | Same-row candidates | Template repeat groups |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for item in report["files"]:
        lines.append(
            f"| {Path(item['file']).name} | {item['row_count']} | "
            f"{len(item['exact_duplicate_groups'])} | {len(item['exact_conflict_groups'])} | "
            f"{len(item['signature_conflict_groups'])} | {len(item['fuzzy_conflicts'])} | "
            f"{len(item['same_row_multi_logical_candidates'])} | "
            f"{len(item['template_repeat_groups'])} |"
        )
    lines.append("")
    lines.append("## Conflict Details")
    lines.append("")
    for item in report["files"]:
        if (
            not item["exact_conflict_groups"]
            and not item["signature_conflict_groups"]
            and not item["fuzzy_conflicts"]
            and not item["same_row_multi_logical_candidates"]
            and not item["template_repeat_groups"]
        ):
            continue
        lines.append(f"### {Path(item['file']).name}")
        lines.append("")
        for grp in item["exact_conflict_groups"]:
            lines.append(
                f"- Exact conflict rows `{grp['rows']}` | answers `{grp['answers']}` | "
                f"question: `{grp['question']}`"
            )
        for grp in item["signature_conflict_groups"][:10]:
            lines.append(
                f"- Signature conflict rows `{grp['rows']}` | answers `{grp['answers']}` | "
                f"signature: `{grp['signature']}`"
            )
        for pair in item["fuzzy_conflicts"][:10]:
            lines.append(
                f"- Fuzzy conflict `{pair['row_1']}/{pair['row_2']}` score `{pair['score']}` "
                f"| answers `{pair['answer_1']}/{pair['answer_2']}`"
            )
        for candidate in item["same_row_multi_logical_candidates"][:10]:
            lines.append(
                f"- Same-row candidate row `{candidate['row']}` | "
                f"reason: `{candidate['reason']}`"
            )
        for group in item["template_repeat_groups"][:10]:
            lines.append(
                f"- Template-repeat family `{group['family']}` | size `{group['size']}` "
                f"| rows `{group['rows']}` | answer_count `{group['answer_count']}`"
            )
        lines.append("")
    return "\n".join(lines)
