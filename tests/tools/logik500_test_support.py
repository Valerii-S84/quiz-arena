from __future__ import annotations

import csv
from pathlib import Path

import build_logik500_bank as builder
import pytest

HEADER = [
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
    "status",
]


def row(key: str, question: str, *, level: str = "A1", category: str = "Logik") -> dict[str, str]:
    return {
        "quiz_id": key,
        "question": question,
        "option_1": "A",
        "option_2": "B",
        "option_3": "C",
        "option_4": "D",
        "correct_option_id": "1",
        "correct_answer": "A",
        "explanation": "Erklaerung.",
        "level": level,
        "category": category,
        "key": key,
        "status": "ready",
    }


def write_source(path: Path, rows: list[dict[str, str]], header: list[str] = HEADER) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def read_output(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def patch_builder(
    monkeypatch: pytest.MonkeyPatch,
    *,
    source_files: list[tuple[str, Path]],
    output_file: Path,
    target_count: int,
    curated_extras: dict[tuple[str, int], str] | None = None,
) -> None:
    monkeypatch.setattr(builder, "SOURCE_FILES", source_files)
    monkeypatch.setattr(builder, "OUTPUT_FILE", output_file)
    monkeypatch.setattr(builder, "TARGET_COUNT", target_count)
    monkeypatch.setattr(builder, "CURATED_EXTRAS", curated_extras or {})
