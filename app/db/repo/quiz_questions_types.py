from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class QuizQuestionPoolChange:
    question_id: str
    mode_code: str
    level: str
    source_file: str
    category: str
    question_text: str
    option_1: str
    option_2: str
    option_3: str
    option_4: str
    correct_option_id: int
    status: str
    quick_mix_eligible: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class QuizQuestionPoolCandidate:
    question_id: str
    level: str
    source_file: str
    category: str
    question_text: str | None = None
    option_1: str | None = None
    option_2: str | None = None
    option_3: str | None = None
    option_4: str | None = None
    correct_option_id: int | None = None
