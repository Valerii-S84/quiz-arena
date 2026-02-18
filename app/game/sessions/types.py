from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(slots=True)
class SessionQuestionView:
    session_id: UUID
    question_id: str
    text: str
    options: tuple[str, str, str, str]
    mode_code: str
    source: str


@dataclass(slots=True)
class StartSessionResult:
    session: SessionQuestionView
    energy_free: int
    energy_paid: int
    idempotent_replay: bool


@dataclass(slots=True)
class AnswerSessionResult:
    session_id: UUID
    question_id: str
    is_correct: bool
    current_streak: int
    best_streak: int
    idempotent_replay: bool
    mode_code: str | None = None
    source: str | None = None
    selected_answer_text: str | None = None
    correct_answer_text: str | None = None
