from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class QuizQuestion:
    question_id: str
    text: str
    options: tuple[str, str, str, str]
    correct_option: int
    level: str | None = None
    category: str | None = None
