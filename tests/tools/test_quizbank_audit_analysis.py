from __future__ import annotations

from pathlib import Path
from typing import Any

from quizbank_audit_analysis import audit_table, make_action_plan
from quizbank_audit_io import TableData

BASE_ROW: dict[str, Any] = {
    "quiz_id": "q1",
    "question": "Was ist richtig?",
    "option_1": "A",
    "option_2": "B",
    "option_3": "C",
    "option_4": "D",
    "correct_option_id": "1",
    "correct_answer": "B",
    "explanation": "Darum.",
    "key": "key-1",
    "level": "A1",
    "category": "Grammar",
    "status": "ready",
    "created_at": "2026-04-29T10:00:00Z",
}


def _table(rows: list[dict[str, Any]], columns: list[str] | None = None) -> TableData:
    return TableData(
        columns=columns or list(BASE_ROW),
        rows=rows,
        parser="csv",
        warnings=[],
    )


def _row(row_number: int, **overrides: Any) -> dict[str, Any]:
    row = dict(BASE_ROW)
    row.update({"_row": row_number}, **overrides)
    return row


def test_audit_table_reports_ready_file() -> None:
    report = audit_table(Path("QuizBank/ready.csv"), _table([_row(2)]))

    assert report["file"] == "QuizBank/ready.csv"
    assert report["readiness"] == "ready"
    assert report["severity"] == {"critical": 0, "high": 0, "medium": 0}
    assert make_action_plan(report) == [
        "No blocking issues detected. Keep file under regression QA."
    ]


def test_audit_table_collects_schema_and_row_issues() -> None:
    columns = [column for column in BASE_ROW if column != "category"]
    report = audit_table(
        Path("QuizBank/issues.csv"),
        _table(
            [
                _row(
                    2,
                    quiz_id="",
                    question="Was  ist richtig ",
                    correct_option_id="x",
                    correct_answer="Z",
                    key="dup",
                    status="draft",
                    created_at="not-a-date",
                ),
                _row(
                    3,
                    question="Was ist richtig",
                    correct_answer="X",
                    key="dup",
                    explanation="Keine Punktuation",
                ),
            ],
            columns=columns,
        ),
    )

    assert report["readiness"] == "needs_fix"
    assert report["missing_required_columns"] == ["category"]
    assert report["missing_required_counts"] == {"quiz_id": 1}
    assert report["invalid_correct_option_id_count"] == 1
    assert report["mismatch_correct_answer_count"] == 1
    assert report["answer_not_in_options_count"] == 1
    assert report["duplicate_question_group_count"] == 1
    assert report["ambiguous_question_group_count"] == 1
    assert report["duplicate_key_group_count"] == 1
    assert report["date_parse_issue_count"] == 1
    assert report["status_distribution"] == {"draft": 1, "ready": 1}


def test_audit_table_marks_cleanup_only_duplicates_as_ready_with_cleanup() -> None:
    report = audit_table(
        Path("QuizBank/cleanup.csv"),
        _table(
            [
                _row(2, key="key-1"),
                _row(3, quiz_id="q2", key="key-2"),
            ]
        ),
    )

    assert report["readiness"] == "ready_with_cleanup"
    assert report["duplicate_question_group_count"] == 1
    assert report["ambiguous_question_group_count"] == 0
    assert report["severity"] == {"critical": 0, "high": 0, "medium": 1}


def test_audit_table_accepts_integer_correct_option_id() -> None:
    report = audit_table(
        Path("QuizBank/int-option.csv"),
        _table([_row(2, correct_option_id=1)]),
    )

    assert report["invalid_correct_option_id_count"] == 0
    assert report["mismatch_correct_answer_count"] == 0
    assert report["answer_not_in_options_count"] == 0


def test_make_action_plan_lists_relevant_fixes() -> None:
    report = audit_table(
        Path("QuizBank/issues.csv"),
        _table(
            [
                _row(2, question="Frage ohne Endzeichen", explanation="Ohne Punkt"),
                _row(3, option_1="A  A", key="unique-2", created_at="bad-date"),
            ]
        ),
    )

    actions = make_action_plan(report)

    assert "Normalize whitespace in questions, options, explanations and keys." in actions
    assert "Normalize timestamp format to ISO 8601." in actions
    assert "Review question punctuation and end marks." in actions
    assert "Ensure explanations end with punctuation." in actions
