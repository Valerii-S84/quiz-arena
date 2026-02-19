from __future__ import annotations

import argparse
import asyncio
import csv
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models.quiz_questions import QuizQuestion
from app.db.session import SessionLocal
from app.game.questions.catalog import QUIZBANK_FILE_TO_MODE_CODE

SKIP_FILES = {"logik_luecke_sheet_template.csv"}
REQUIRED_COLUMNS = {
    "quiz_id",
    "question",
    "option_1",
    "option_2",
    "option_3",
    "option_4",
    "correct_option_id",
    "correct_answer",
    "explanation",
    "level",
    "category",
    "key",
}


@dataclass(slots=True)
class ImportSummary:
    total_rows_read: int = 0
    total_rows_imported: int = 0
    skipped_not_ready: int = 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import QuizBank CSV files into quiz_questions.")
    parser.add_argument("--input-dir", type=Path, default=Path("QuizBank"))
    parser.add_argument(
        "--replace-all",
        action="store_true",
        help="Delete existing rows from quiz_questions before import.",
    )
    parser.add_argument(
        "--allow-unmapped",
        action="store_true",
        help="Skip CSV files that are not mapped to a mode code.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - fieldnames)
        if missing:
            missing_str = ", ".join(missing)
            raise ValueError(f"{path.name}: missing required columns: {missing_str}")
        return [dict(row) for row in reader]


def _build_records(args: argparse.Namespace) -> tuple[list[dict[str, Any]], ImportSummary, Counter[str]]:
    if not args.input_dir.exists():
        raise ValueError(f"input directory does not exist: {args.input_dir}")

    summary = ImportSummary()
    by_mode = Counter[str]()
    records: list[dict[str, Any]] = []
    seen_question_ids: set[str] = set()

    files = sorted(p for p in args.input_dir.iterdir() if p.is_file() and p.suffix.lower() == ".csv")
    for path in files:
        if path.name in SKIP_FILES:
            continue

        mode_code = QUIZBANK_FILE_TO_MODE_CODE.get(path.name)
        if mode_code is None:
            if args.allow_unmapped:
                continue
            raise ValueError(
                f"{path.name}: file is not mapped to mode_code. "
                "Update app/game/questions/catalog.py."
            )

        rows = _read_csv(path)
        summary.total_rows_read += len(rows)
        for row_index, row in enumerate(rows, start=2):
            source_status = _norm(row.get("status", "ready"))
            if source_status not in {"", "ready", "active"}:
                summary.skipped_not_ready += 1
                continue

            question_id = (row.get("quiz_id") or "").strip()
            if not question_id:
                raise ValueError(f"{path.name}:{row_index}: empty quiz_id")
            if len(question_id) > 64:
                raise ValueError(f"{path.name}:{row_index}: quiz_id exceeds 64 characters")
            if question_id in seen_question_ids:
                raise ValueError(f"{path.name}:{row_index}: duplicate quiz_id in import set: {question_id}")
            seen_question_ids.add(question_id)

            options = [
                (row.get("option_1") or "").strip(),
                (row.get("option_2") or "").strip(),
                (row.get("option_3") or "").strip(),
                (row.get("option_4") or "").strip(),
            ]
            if not all(options):
                raise ValueError(f"{path.name}:{row_index}: all options must be non-empty")

            raw_correct_option = (row.get("correct_option_id") or "").strip()
            if raw_correct_option not in {"0", "1", "2", "3"}:
                raise ValueError(
                    f"{path.name}:{row_index}: invalid correct_option_id={raw_correct_option!r}"
                )
            correct_option_id = int(raw_correct_option)

            correct_answer = (row.get("correct_answer") or "").strip()
            expected_answer = options[correct_option_id]
            if _norm(correct_answer) != _norm(expected_answer):
                raise ValueError(
                    f"{path.name}:{row_index}: correct_answer mismatch. "
                    f"expected={expected_answer!r}, got={correct_answer!r}"
                )

            question_text = (row.get("question") or "").strip()
            if not question_text:
                raise ValueError(f"{path.name}:{row_index}: empty question")

            explanation = (row.get("explanation") or "").strip()
            if not explanation:
                raise ValueError(f"{path.name}:{row_index}: empty explanation")

            level = (row.get("level") or "").strip().upper() or "A1"
            category = (row.get("category") or "").strip() or "General"
            key = (row.get("key") or "").strip() or question_id

            now_utc = datetime.now(timezone.utc)
            records.append(
                {
                    "question_id": question_id,
                    "mode_code": mode_code,
                    "source_file": path.name,
                    "level": level,
                    "category": category,
                    "question_text": question_text,
                    "option_1": options[0],
                    "option_2": options[1],
                    "option_3": options[2],
                    "option_4": options[3],
                    "correct_option_id": correct_option_id,
                    "correct_answer": expected_answer,
                    "explanation": explanation,
                    "key": key,
                    "status": "ACTIVE",
                    "created_at": now_utc,
                    "updated_at": now_utc,
                }
            )
            by_mode[mode_code] += 1

    summary.total_rows_imported = len(records)
    return records, summary, by_mode


def _chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


async def _persist_records(records: list[dict[str, Any]], *, replace_all: bool) -> None:
    if not records:
        raise ValueError("no importable rows found")

    async with SessionLocal.begin() as session:
        if replace_all:
            await session.execute(delete(QuizQuestion))

        for chunk in _chunks(records, 1000):
            stmt = pg_insert(QuizQuestion).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=[QuizQuestion.question_id],
                set_={
                    "mode_code": stmt.excluded.mode_code,
                    "source_file": stmt.excluded.source_file,
                    "level": stmt.excluded.level,
                    "category": stmt.excluded.category,
                    "question_text": stmt.excluded.question_text,
                    "option_1": stmt.excluded.option_1,
                    "option_2": stmt.excluded.option_2,
                    "option_3": stmt.excluded.option_3,
                    "option_4": stmt.excluded.option_4,
                    "correct_option_id": stmt.excluded.correct_option_id,
                    "correct_answer": stmt.excluded.correct_answer,
                    "explanation": stmt.excluded.explanation,
                    "key": stmt.excluded.key,
                    "status": stmt.excluded.status,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)


async def _run() -> int:
    args = _parse_args()
    records, summary, by_mode = _build_records(args)

    if not args.dry_run:
        await _persist_records(records, replace_all=args.replace_all)

    mode_stats = ", ".join(f"{mode}={count}" for mode, count in sorted(by_mode.items()))
    print(  # noqa: T201
        "quizbank_import "
        f"rows_read={summary.total_rows_read} "
        f"rows_imported={summary.total_rows_imported} "
        f"skipped_not_ready={summary.skipped_not_ready} "
        f"replace_all={args.replace_all} "
        f"dry_run={args.dry_run}"
    )
    print(f"quizbank_import_by_mode {mode_stats}")  # noqa: T201
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
