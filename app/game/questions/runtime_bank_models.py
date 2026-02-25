from __future__ import annotations

from app.db.models.quiz_questions import QuizQuestion as QuizQuestionRecord
from app.game.questions.types import QuizQuestion

QUICK_MIX_MODE_CODE = "QUICK_MIX_A1A2"
ALL_ACTIVE_SCOPE_CODE = "__ALL_ACTIVE__"


def to_quiz_question(record: QuizQuestionRecord) -> QuizQuestion:
    return QuizQuestion(
        question_id=record.question_id,
        text=record.question_text,
        options=(
            record.option_1,
            record.option_2,
            record.option_3,
            record.option_4,
        ),
        correct_option=record.correct_option_id,
        mode_code=record.mode_code,
        level=record.level,
        category=record.category,
    )
