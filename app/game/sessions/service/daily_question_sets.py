from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.daily_question_sets_repo import DailyQuestionSetsRepo
from app.db.repo.quiz_questions_repo import QuizQuestionsRepo
from app.game.questions.catalog import DAILY_CHALLENGE_SOURCE_MODE
from app.game.questions.runtime_bank_filters import pick_from_pool

from .constants import DAILY_CHALLENGE_TOTAL_QUESTIONS

DAILY_LEVEL_CHAIN: tuple[str, ...] = ("A1", "A2", "B1")
DAILY_POSITION_PREFERRED_LEVELS: tuple[str, ...] = (
    "A1",
    "A1",
    "A2",
    "A2",
    "B1",
    "B1",
    "B1",
)


def _daily_selection_seed(*, berlin_date: date, position: int) -> str:
    return f"daily:{berlin_date.isoformat()}:{DAILY_CHALLENGE_SOURCE_MODE}:{position}"


def _daily_level_window_for_position(position: int) -> tuple[str, tuple[str, ...]]:
    index = min(max(position - 1, 0), len(DAILY_POSITION_PREFERRED_LEVELS) - 1)
    preferred_level = DAILY_POSITION_PREFERRED_LEVELS[index]
    max_chain_index = DAILY_LEVEL_CHAIN.index(preferred_level)
    return preferred_level, DAILY_LEVEL_CHAIN[: max_chain_index + 1]


async def _build_daily_question_ids(
    session: AsyncSession,
    *,
    berlin_date: date,
) -> tuple[str, ...]:
    candidate_ids_cache: dict[tuple[str, ...] | None, list[str]] = {}

    async def _cached_candidate_ids(preferred_levels: tuple[str, ...] | None) -> list[str]:
        if preferred_levels not in candidate_ids_cache:
            candidate_ids_cache[preferred_levels] = (
                await QuizQuestionsRepo.list_question_ids_for_mode(
                    session,
                    mode_code=DAILY_CHALLENGE_SOURCE_MODE,
                    preferred_levels=preferred_levels,
                )
            )
        return candidate_ids_cache[preferred_levels]

    selected_question_ids: list[str] = []
    for position in range(1, DAILY_CHALLENGE_TOTAL_QUESTIONS + 1):
        seed = _daily_selection_seed(berlin_date=berlin_date, position=position)
        preferred_level, allowed_levels = _daily_level_window_for_position(position)
        candidate_ids = await _cached_candidate_ids((preferred_level,))
        if not candidate_ids:
            candidate_ids = await _cached_candidate_ids(allowed_levels)
        if not candidate_ids:
            candidate_ids = await _cached_candidate_ids(DAILY_LEVEL_CHAIN)
        if not candidate_ids:
            break

        selected = pick_from_pool(
            candidate_ids,
            exclude_question_ids=selected_question_ids,
            selection_seed=seed,
        )
        if selected is None:
            selected = pick_from_pool(
                candidate_ids,
                exclude_question_ids=(),
                selection_seed=seed,
            )
        if selected is None:
            break
        selected_question_ids.append(selected)
    return tuple(selected_question_ids)


async def _fallback_daily_question_id(
    session: AsyncSession,
    *,
    berlin_date: date,
) -> str:
    from app.game.sessions import service as service_module

    question = await service_module.select_question_for_mode(
        session,
        "DAILY_CHALLENGE",
        local_date_berlin=berlin_date,
        recent_question_ids=(),
        selection_seed=f"daily:fallback:{berlin_date.isoformat()}",
        preferred_level=DAILY_POSITION_PREFERRED_LEVELS[0],
        allowed_levels=DAILY_LEVEL_CHAIN,
    )
    return question.question_id


async def ensure_daily_question_set(
    session: AsyncSession,
    *,
    berlin_date: date,
) -> tuple[str, ...]:
    existing = await DailyQuestionSetsRepo.list_question_ids_for_date(
        session,
        berlin_date=berlin_date,
    )
    if len(existing) >= DAILY_CHALLENGE_TOTAL_QUESTIONS:
        return existing[:DAILY_CHALLENGE_TOTAL_QUESTIONS]

    generated = await _build_daily_question_ids(session, berlin_date=berlin_date)
    if generated:
        resolved = generated
        if len(generated) < DAILY_CHALLENGE_TOTAL_QUESTIONS:
            resolved = generated + (generated[0],) * (
                DAILY_CHALLENGE_TOTAL_QUESTIONS - len(generated)
            )
        await DailyQuestionSetsRepo.upsert_question_ids(
            session,
            berlin_date=berlin_date,
            question_ids=resolved[:DAILY_CHALLENGE_TOTAL_QUESTIONS],
        )
        existing = await DailyQuestionSetsRepo.list_question_ids_for_date(
            session,
            berlin_date=berlin_date,
        )
        if len(existing) >= DAILY_CHALLENGE_TOTAL_QUESTIONS:
            return existing[:DAILY_CHALLENGE_TOTAL_QUESTIONS]

    fallback_question_id = await _fallback_daily_question_id(session, berlin_date=berlin_date)
    fallback_set = (fallback_question_id,) * DAILY_CHALLENGE_TOTAL_QUESTIONS
    await DailyQuestionSetsRepo.upsert_question_ids(
        session,
        berlin_date=berlin_date,
        question_ids=fallback_set,
    )
    return fallback_set
