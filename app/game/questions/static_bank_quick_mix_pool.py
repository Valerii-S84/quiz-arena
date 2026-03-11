from __future__ import annotations

from app.game.questions.static_bank_quick_mix_pool_a import _QUICK_MIX_ITEMS_A
from app.game.questions.static_bank_quick_mix_pool_b import _QUICK_MIX_ITEMS_B
from app.game.questions.types import QuizQuestion

_QUICK_MIX_ITEMS = _QUICK_MIX_ITEMS_A + _QUICK_MIX_ITEMS_B


def build_quick_mix_pool() -> tuple[QuizQuestion, ...]:
    return tuple(
        QuizQuestion(
            question_id=question_id,
            text=text,
            options=options,
            correct_option=correct_option,
            level=level,
            category=category,
        )
        for question_id, text, options, correct_option, level, category in _QUICK_MIX_ITEMS
    )
