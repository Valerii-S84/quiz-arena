from __future__ import annotations

from datetime import date
from typing import Sequence

from app.game.questions.static_bank import get_question_by_id as get_question_by_id_fallback
from app.game.questions.static_bank import get_question_for_mode as get_question_for_mode_fallback
from app.game.questions.static_bank import (
    select_question_for_mode as select_question_for_mode_fallback,
)
from app.game.questions.types import QuizQuestion


def fallback_get_question_by_id(
    mode_code: str,
    *,
    question_id: str,
    local_date_berlin: date,
) -> QuizQuestion | None:
    return get_question_by_id_fallback(
        mode_code,
        question_id=question_id,
        local_date_berlin=local_date_berlin,
    )


def fallback_select_question_for_mode(
    mode_code: str,
    *,
    local_date_berlin: date,
    recent_question_ids: Sequence[str],
    selection_seed: str,
    preferred_level: str | None = None,
) -> QuizQuestion:
    return select_question_for_mode_fallback(
        mode_code,
        local_date_berlin=local_date_berlin,
        recent_question_ids=recent_question_ids,
        selection_seed=selection_seed,
        preferred_level=preferred_level,
    )


def fallback_get_question_for_mode(
    mode_code: str,
    *,
    local_date_berlin: date,
) -> QuizQuestion:
    return get_question_for_mode_fallback(mode_code, local_date_berlin=local_date_berlin)
