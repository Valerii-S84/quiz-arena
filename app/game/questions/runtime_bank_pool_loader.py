from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.quiz_questions_repo import QuizQuestionPoolCandidate
from app.game.questions.catalog import mode_requires_quick_mix_eligible


@dataclass(frozen=True, slots=True)
class PoolLoadResult:
    question_ids: tuple[str, ...]
    candidates_by_id: dict[str, QuizQuestionPoolCandidate]
    updated_at_watermark: datetime


def _repo():
    from app.game.questions import runtime_bank

    return runtime_bank.QuizQuestionsRepo


async def load_pool_ids(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> tuple[str, ...]:
    return tuple(
        candidate.question_id
        for candidate in await load_pool_candidates(
            session,
            mode_code=mode_code,
            preferred_levels=preferred_levels,
        )
    )


async def load_pool_candidates(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> tuple[QuizQuestionPoolCandidate, ...]:
    repo = _repo()
    if mode_requires_quick_mix_eligible(mode_code):
        candidates = await repo.list_question_candidates_all_active(
            session,
            exclude_question_ids=None,
            preferred_levels=preferred_levels,
            require_quick_mix_eligible=True,
        )
    else:
        candidates = await repo.list_question_candidates_for_mode(
            session,
            mode_code=mode_code,
            exclude_question_ids=None,
            preferred_levels=preferred_levels,
        )
    return tuple(candidates)


async def load_full_pool_snapshot(
    session: AsyncSession,
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
) -> PoolLoadResult:
    loaded_candidates = await load_pool_candidates(
        session,
        mode_code=mode_code,
        preferred_levels=preferred_levels,
    )
    return PoolLoadResult(
        question_ids=tuple(candidate.question_id for candidate in loaded_candidates),
        candidates_by_id={candidate.question_id: candidate for candidate in loaded_candidates},
        updated_at_watermark=datetime.now(timezone.utc),
    )
