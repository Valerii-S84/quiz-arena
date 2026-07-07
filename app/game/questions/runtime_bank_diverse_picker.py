from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_questions import QuizQuestion as QuizQuestionRecord
from app.db.repo.quiz_questions_repo import QuizQuestionPoolCandidate
from app.game.questions.runtime_bank_filters import (
    QuestionSelectionMetadata,
    filter_active_records,
    pick_from_pool,
    select_diverse_record,
)
from app.game.questions.runtime_bank_pool import _repo


def _pick_from_pool(
    candidate_ids: Sequence[str],
    *,
    exclude_question_ids: Sequence[str],
    selection_seed: str,
) -> str | None:
    return pick_from_pool(
        candidate_ids,
        exclude_question_ids=exclude_question_ids,
        selection_seed=selection_seed,
    )


async def _list_active_records_by_id(
    session: AsyncSession,
    question_ids: Sequence[str],
) -> list[QuizQuestionRecord]:
    unique_ids = tuple(dict.fromkeys(question_ids))
    if not unique_ids:
        return []

    records = await _repo().list_by_ids(session, question_ids=unique_ids)
    return filter_active_records(records, ids=unique_ids)


async def _pick_diverse_from_pool(
    session: AsyncSession,
    candidate_pool: Sequence[QuizQuestionPoolCandidate],
    *,
    exclude_question_ids: Sequence[str],
    previous_question_ids: Sequence[str],
    selection_seed: str,
) -> str | None:
    if not candidate_pool or not previous_question_ids:
        return None

    excluded = set(exclude_question_ids)
    eligible_candidates = [
        candidate for candidate in candidate_pool if candidate.question_id not in excluded
    ]
    fallback_to_duplicate = False
    if not eligible_candidates:
        eligible_candidates = list(candidate_pool)
        fallback_to_duplicate = True

    pool_by_id = {candidate.question_id: candidate for candidate in candidate_pool}
    previous_records: list[QuestionSelectionMetadata] = [
        candidate
        for question_id in previous_question_ids
        if (candidate := pool_by_id.get(question_id))
    ]
    loaded_ids = {record.question_id for record in previous_records}
    missing_previous_ids = [
        question_id for question_id in previous_question_ids if question_id not in loaded_ids
    ]
    previous_records.extend(await _list_active_records_by_id(session, missing_previous_ids))
    selected = select_diverse_record(
        candidate_records=eligible_candidates,
        previous_records=previous_records,
        selection_seed=selection_seed,
    )
    if selected is None:
        return None
    if not fallback_to_duplicate and selected.question_id in excluded:
        return None
    return selected.question_id
