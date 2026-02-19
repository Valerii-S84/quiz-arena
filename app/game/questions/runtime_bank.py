from __future__ import annotations

import hashlib
from datetime import date
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_questions import QuizQuestion as QuizQuestionRecord
from app.db.repo.quiz_questions_repo import QuizQuestionsRepo
from app.game.questions.catalog import DAILY_CHALLENGE_SOURCE_MODE
from app.game.questions.static_bank import (
    get_question_by_id as get_question_by_id_fallback,
)
from app.game.questions.static_bank import (
    get_question_for_mode as get_question_for_mode_fallback,
)
from app.game.questions.static_bank import (
    select_question_for_mode as select_question_for_mode_fallback,
)
from app.game.questions.types import QuizQuestion

QUICK_MIX_MODE_CODE = "QUICK_MIX_A1A2"


def _stable_index(seed: str, size: int) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % size


def _to_quiz_question(record: QuizQuestionRecord) -> QuizQuestion:
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
    )


async def _pick_from_mode(
    session: AsyncSession,
    *,
    mode_code: str,
    recent_question_ids: Sequence[str],
    selection_seed: str,
) -> QuizQuestion | None:
    if mode_code == QUICK_MIX_MODE_CODE:
        candidate_ids = await QuizQuestionsRepo.list_question_ids_all_active(
            session,
            exclude_question_ids=recent_question_ids,
        )
    else:
        candidate_ids = await QuizQuestionsRepo.list_question_ids_for_mode(
            session,
            mode_code=mode_code,
            exclude_question_ids=recent_question_ids,
        )
    if not candidate_ids:
        if mode_code == QUICK_MIX_MODE_CODE:
            candidate_ids = await QuizQuestionsRepo.list_question_ids_all_active(
                session,
                exclude_question_ids=None,
            )
        else:
            candidate_ids = await QuizQuestionsRepo.list_question_ids_for_mode(
                session,
                mode_code=mode_code,
                exclude_question_ids=None,
            )
    if not candidate_ids:
        return None

    selected_id = candidate_ids[_stable_index(selection_seed, len(candidate_ids))]
    selected = await QuizQuestionsRepo.get_by_id(session, selected_id)
    if selected is None:
        return None
    return _to_quiz_question(selected)


async def get_question_by_id(
    session: AsyncSession,
    mode_code: str,
    *,
    question_id: str,
    local_date_berlin: date,
) -> QuizQuestion | None:
    selected = await QuizQuestionsRepo.get_by_id(session, question_id)
    if selected is not None and selected.status == "ACTIVE":
        return _to_quiz_question(selected)
    return get_question_by_id_fallback(
        mode_code,
        question_id=question_id,
        local_date_berlin=local_date_berlin,
    )


async def select_question_for_mode(
    session: AsyncSession,
    mode_code: str,
    *,
    local_date_berlin: date,
    recent_question_ids: Sequence[str],
    selection_seed: str,
) -> QuizQuestion:
    db_mode_code = DAILY_CHALLENGE_SOURCE_MODE if mode_code == "DAILY_CHALLENGE" else mode_code
    db_seed = (
        f"daily:{local_date_berlin.isoformat()}:{db_mode_code}"
        if mode_code == "DAILY_CHALLENGE"
        else selection_seed
    )
    db_recent = () if mode_code == "DAILY_CHALLENGE" else recent_question_ids
    selected = await _pick_from_mode(
        session,
        mode_code=db_mode_code,
        recent_question_ids=db_recent,
        selection_seed=db_seed,
    )
    if selected is not None:
        return selected

    return select_question_for_mode_fallback(
        mode_code,
        local_date_berlin=local_date_berlin,
        recent_question_ids=recent_question_ids,
        selection_seed=selection_seed,
    )


async def get_question_for_mode(
    session: AsyncSession,
    mode_code: str,
    *,
    local_date_berlin: date,
) -> QuizQuestion:
    selected = await select_question_for_mode(
        session,
        mode_code,
        local_date_berlin=local_date_berlin,
        recent_question_ids=(),
        selection_seed=f"fallback:{mode_code}:{local_date_berlin.isoformat()}",
    )
    if selected is not None:
        return selected
    return get_question_for_mode_fallback(mode_code, local_date_berlin=local_date_berlin)
