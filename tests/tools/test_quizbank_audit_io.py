from __future__ import annotations

from pathlib import Path

from quizbank_audit_io import normalize, parse_date, read_csv_table, read_table


def test_normalize_collapses_whitespace_and_dash_variants() -> None:
    assert normalize("  A\u2011B\u2013C\u2014D   E  ") == "a-b-c-d e"


def test_parse_date_accepts_empty_and_iso_values() -> None:
    assert parse_date(None) is True
    assert parse_date("") is True
    assert parse_date("2026-04-29T10:30:00Z") is True


def test_parse_date_rejects_invalid_text() -> None:
    assert parse_date("29.04.2026") is False


def test_read_csv_table_strips_headers_and_tracks_source_rows(tmp_path: Path) -> None:
    table_path = tmp_path / "bank.csv"
    table_path.write_text(" quiz_id ,question\nq1,Frage?\nq2,Noch eine Frage?\n", encoding="utf-8")

    table = read_csv_table(table_path)

    assert table.columns == ["quiz_id", "question"]
    assert table.rows == [
        {"quiz_id": "q1", "question": "Frage?", "_row": 2},
        {"quiz_id": "q2", "question": "Noch eine Frage?", "_row": 3},
    ]
    assert table.parser == "csv"
    assert table.warnings == []


def test_read_csv_table_reports_missing_header(tmp_path: Path) -> None:
    table_path = tmp_path / "empty.csv"
    table_path.write_text("", encoding="utf-8")

    table = read_csv_table(table_path)

    assert table.columns == []
    assert table.rows == []
    assert table.parser == "csv"
    assert table.warnings == ["empty.csv: missing header"]


def test_read_table_dispatches_csv_reader(tmp_path: Path) -> None:
    table_path = tmp_path / "bank.csv"
    table_path.write_text("quiz_id\nq1\n", encoding="utf-8")

    table = read_table(table_path)

    assert table.columns == ["quiz_id"]
    assert table.rows == [{"quiz_id": "q1", "_row": 2}]


def test_read_table_reports_unsupported_extension(tmp_path: Path) -> None:
    table = read_table(tmp_path / "bank.txt")

    assert table.columns == []
    assert table.rows == []
    assert table.parser == "unknown"
    assert table.warnings == ["bank.txt: unsupported extension .txt"]
