from __future__ import annotations

from app.db.models.quiz_questions import QuizQuestion as QuizQuestionRecord
from app.game.questions.types import QuizQuestion

QUICK_MIX_MODE_CODE = "QUICK_MIX_A1A2"
QUICK_MIX_SCOPE_CODE = "__QUICK_MIX_ELIGIBLE__"
ALL_ACTIVE_SCOPE_CODE = QUICK_MIX_SCOPE_CODE


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
        level=record.level,
        category=record.category,
    )
