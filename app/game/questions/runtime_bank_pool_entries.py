from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.quiz_questions_repo import QuizQuestionPoolCandidate
from app.game.questions.runtime_bank_pool_loader import load_full_pool_snapshot
from app.game.questions.runtime_bank_pool_membership import refresh_pool_candidates
from app.game.questions.types import QuizQuestion


@dataclass(slots=True)
class PoolCacheEntry:
    loaded_at_mono: float
    question_ids: tuple[str, ...]
    candidates_by_id: dict[str, QuizQuestionPoolCandidate]
    updated_at_watermark: datetime


@dataclass(slots=True)
class QuestionCacheEntry:
    loaded_at_mono: float
    question: QuizQuestion


def _repo():
    from app.game.questions import runtime_bank

    return runtime_bank.QuizQuestionsRepo


async def build_full_pool_entry(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
    loaded_at_mono: Callable[[], float],
) -> PoolCacheEntry:
    snapshot = await load_full_pool_snapshot(
        session,
        mode_code=mode_code,
        preferred_levels=preferred_levels,
    )
    return PoolCacheEntry(
        loaded_at_mono=loaded_at_mono(),
        question_ids=snapshot.question_ids,
        candidates_by_id=snapshot.candidates_by_id,
        updated_at_watermark=snapshot.updated_at_watermark,
    )


async def build_incremental_pool_entry(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
    cached: PoolCacheEntry,
    question_cache: dict[str, QuestionCacheEntry],
    loaded_at_mono: Callable[[], float],
) -> PoolCacheEntry:
    changes = await _repo().list_question_pool_changes_since(
        session,
        since_updated_at=cached.updated_at_watermark,
    )
    if not changes:
        return PoolCacheEntry(
            loaded_at_mono=loaded_at_mono(),
            question_ids=cached.question_ids,
            candidates_by_id=cached.candidates_by_id,
            updated_at_watermark=cached.updated_at_watermark,
        )

    refreshed = refresh_pool_candidates(
        changes,
        mode_code=mode_code,
        preferred_levels=preferred_levels,
        cached_candidates_by_id=cached.candidates_by_id,
        cached_updated_at_watermark=cached.updated_at_watermark,
    )
    for question_id in refreshed.invalidated_question_ids:
        question_cache.pop(question_id, None)
    return PoolCacheEntry(
        loaded_at_mono=loaded_at_mono(),
        question_ids=refreshed.question_ids,
        candidates_by_id=refreshed.candidates_by_id,
        updated_at_watermark=refreshed.updated_at_watermark,
    )
