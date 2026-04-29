from __future__ import annotations

from quizbank_audit_report import build_markdown


def _file_report(**overrides: object) -> dict[str, object]:
    report: dict[str, object] = {
        "file": "QuizBank/ready.csv",
        "row_count": 2,
        "readiness": "ready",
        "severity": {"critical": 0, "high": 0, "medium": 0},
        "ambiguous_question_group_count": 0,
        "duplicate_question_group_count": 0,
        "missing_required_columns": [],
        "missing_required_counts": {},
        "invalid_correct_option_id_count": 0,
        "mismatch_correct_answer_count": 0,
        "answer_not_in_options_count": 0,
        "duplicate_key_group_count": 0,
        "trailing_space_issue_count": 0,
        "double_space_issue_count": 0,
        "date_parse_issue_count": 0,
        "question_terminal_punctuation_issue_count": 0,
        "explanation_terminal_punctuation_issue_count": 0,
    }
    report.update(overrides)
    return report


def test_build_markdown_renders_summary_table_and_action_plan() -> None:
    markdown = build_markdown(
        {
            "generated_at": "2026-04-29T10:00:00+00:00",
            "summary": {"file_count": 2, "row_count": 5},
            "files": [
                _file_report(),
                _file_report(
                    file="QuizBank/issues.csv",
                    row_count=3,
                    readiness="needs_fix",
                    severity={"critical": 1, "high": 0, "medium": 1},
                    missing_required_columns=["category"],
                    trailing_space_issue_count=1,
                ),
            ],
        }
    )

    assert "# QuizBank Audit Report" in markdown
    assert "- Files audited: `2`" in markdown
    assert "| ready.csv | 2 | ready | 0 | 0 | 0 | 0 | 0 |" in markdown
    assert "| issues.csv | 3 | needs_fix | 1 | 0 | 1 | 0 | 0 |" in markdown
    assert "### issues.csv" in markdown
    assert "- Add missing required columns to match ingest schema." in markdown
    assert "- Normalize whitespace in questions, options, explanations and keys." in markdown
