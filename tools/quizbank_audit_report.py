from __future__ import annotations

from pathlib import Path
from typing import Any

from quizbank_audit_analysis import make_action_plan


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# QuizBank Audit Report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at']}`")
    lines.append(f"- Files audited: `{report['summary']['file_count']}`")
    lines.append(f"- Total rows: `{report['summary']['row_count']}`")
    lines.append("")
    lines.append("## Checklist by file")
    lines.append("")
    lines.append(
        "| File | Rows | Readiness | Critical | High | Medium | Ambiguous groups | Duplicate question groups |"
    )
    lines.append("|---|---:|---|---:|---:|---:|---:|---:|")
    for file_report in report["files"]:
        lines.append(
            "| "
            f"{Path(file_report['file']).name} | "
            f"{file_report['row_count']} | "
            f"{file_report['readiness']} | "
            f"{file_report['severity']['critical']} | "
            f"{file_report['severity']['high']} | "
            f"{file_report['severity']['medium']} | "
            f"{file_report['ambiguous_question_group_count']} | "
            f"{file_report['duplicate_question_group_count']} |"
        )

    lines.append("")
    lines.append("## Per-file action plan")
    lines.append("")
    for file_report in report["files"]:
        lines.append(f"### {Path(file_report['file']).name}")
        lines.append("")
        lines.append(
            "- Status: "
            f"`{file_report['readiness']}` "
            f"(critical `{file_report['severity']['critical']}`, "
            f"high `{file_report['severity']['high']}`, "
            f"medium `{file_report['severity']['medium']}`)"
        )
        actions = make_action_plan(file_report)
        for action in actions:
            lines.append(f"- {action}")
        lines.append("")
    return "\n".join(lines)
