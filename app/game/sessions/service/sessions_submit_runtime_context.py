from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.models.quiz_sessions import QuizSession
from app.game.sessions.types import AnswerSessionResult


@dataclass(slots=True)
class AnswerSessionResolution:
    quiz_session: QuizSession | None
    replay_result: AnswerSessionResult | None


@dataclass(slots=True)
class SubmittedAnswerState:
    quiz_session: QuizSession
    question: Any
    is_correct: bool
    selected_option: int


@dataclass(slots=True)
class RegularAnswerResolution:
    friend_snapshot: Any
    friend_round_completed: bool
    friend_waiting_for_opponent: bool
    current_streak: int
    best_streak: int
    next_preferred_level: str | None


@dataclass(slots=True)
class AnswerTextFields:
    selected_answer_text: str | None
    correct_answer_text: str | None
    question_level: str | None


def build_answer_text_fields(submitted_answer: SubmittedAnswerState) -> AnswerTextFields:
    return AnswerTextFields(
        selected_answer_text=submitted_answer.question.options[submitted_answer.selected_option],
        correct_answer_text=submitted_answer.question.options[
            submitted_answer.question.correct_option
        ],
        question_level=submitted_answer.question.level,
    )
