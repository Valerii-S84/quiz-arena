from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.daily_question_sets_repo import DailyQuestionSetsRepo
from app.db.repo.quiz_questions_repo import QuizQuestionPoolCandidate, QuizQuestionsRepo
from app.game.questions.catalog import DAILY_CHALLENGE_SOURCE_MODE, mode_requires_quick_mix_eligible
from app.game.questions.runtime_bank_seed import stable_index

from .constants import DAILY_CHALLENGE_TOTAL_QUESTIONS

DAILY_LEVEL_CHAIN: tuple[str, ...] = ("A1", "A2", "B1")
DAILY_POSITION_PREFERRED_LEVELS: tuple[str, ...] = (
    "A1",
    "A1",
    "A2",
    "A2",
    "A2",
    "B1",
    "B1",
)


def _daily_selection_seed(*, berlin_date: date, position: int) -> str:
    return f"daily:{berlin_date.isoformat()}:{DAILY_CHALLENGE_SOURCE_MODE}:{position}"


def daily_level_window_for_position(position: int) -> tuple[str, tuple[str, ...]]:
    index = min(max(position - 1, 0), len(DAILY_POSITION_PREFERRED_LEVELS) - 1)
    preferred_level = DAILY_POSITION_PREFERRED_LEVELS[index]
    max_chain_index = DAILY_LEVEL_CHAIN.index(preferred_level)
    return preferred_level, DAILY_LEVEL_CHAIN[: max_chain_index + 1]


def is_daily_level_allowed_for_position(*, position: int, level: str | None) -> bool:
    normalized_level = (level or "").strip().upper()
    if not normalized_level:
        return False
    _, allowed_levels = daily_level_window_for_position(position)
    return normalized_level in allowed_levels


def _daily_level_windows_for_position(position: int) -> tuple[tuple[str, ...], ...]:
    preferred_level, allowed_levels = daily_level_window_for_position(position)
    level_windows = ((preferred_level,), allowed_levels, DAILY_LEVEL_CHAIN)
    ordered_unique: list[tuple[str, ...]] = []
    for levels in level_windows:
        if levels not in ordered_unique:
            ordered_unique.append(levels)
    return tuple(ordered_unique)


async def _list_daily_candidates(
    session: AsyncSession,
    *,
    preferred_levels: tuple[str, ...],
) -> list[QuizQuestionPoolCandidate]:
    if mode_requires_quick_mix_eligible(DAILY_CHALLENGE_SOURCE_MODE):
        return await QuizQuestionsRepo.list_question_candidates_all_active(
            session,
            exclude_question_ids=None,
            preferred_levels=preferred_levels,
            require_quick_mix_eligible=True,
        )
    return await QuizQuestionsRepo.list_question_candidates_for_mode(
        session,
        mode_code=DAILY_CHALLENGE_SOURCE_MODE,
        exclude_question_ids=None,
        preferred_levels=preferred_levels,
    )


def _pick_daily_candidate(
    candidates: Sequence[QuizQuestionPoolCandidate],
    *,
    selection_seed: str,
) -> QuizQuestionPoolCandidate | None:
    if not candidates:
        return None
    ordered = sorted(candidates, key=lambda candidate: candidate.question_id)
    return ordered[stable_index(selection_seed, len(ordered))]


def _pick_from_daily_candidate_pools(
    candidate_pools: Sequence[Sequence[QuizQuestionPoolCandidate]],
    *,
    matches: Callable[[QuizQuestionPoolCandidate], bool],
    selection_seed: str,
) -> QuizQuestionPoolCandidate | None:
    for pool in candidate_pools:
        selected = _pick_daily_candidate(
            [candidate for candidate in pool if matches(candidate)],
            selection_seed=selection_seed,
        )
        if selected is not None:
            return selected
    return None


def _select_daily_candidate(
    candidate_pools: Sequence[Sequence[QuizQuestionPoolCandidate]],
    *,
    selected_question_ids: Sequence[str],
    used_source_files: set[str],
    used_categories: set[str],
    selection_seed: str,
) -> QuizQuestionPoolCandidate | None:
    selected_ids = set(selected_question_ids)

    selected = _pick_from_daily_candidate_pools(
        candidate_pools,
        matches=lambda candidate: (
            candidate.question_id not in selected_ids
            and candidate.source_file not in used_source_files
        ),
        selection_seed=selection_seed,
    )
    if selected is not None:
        return selected

    selected = _pick_from_daily_candidate_pools(
        candidate_pools,
        matches=lambda candidate: (
            candidate.question_id not in selected_ids and candidate.category not in used_categories
        ),
        selection_seed=selection_seed,
    )
    if selected is not None:
        return selected

    selected = _pick_from_daily_candidate_pools(
        candidate_pools,
        matches=lambda candidate: candidate.question_id not in selected_ids,
        selection_seed=selection_seed,
    )
    if selected is not None:
        return selected

    return _pick_from_daily_candidate_pools(
        candidate_pools,
        matches=lambda candidate: True,
        selection_seed=selection_seed,
    )


async def _build_daily_question_ids(
    session: AsyncSession,
    *,
    berlin_date: date,
) -> tuple[str, ...]:
    candidates_cache: dict[tuple[str, ...], list[QuizQuestionPoolCandidate]] = {}

    async def _cached_candidates(
        preferred_levels: tuple[str, ...],
    ) -> list[QuizQuestionPoolCandidate]:
        if preferred_levels not in candidates_cache:
            candidates_cache[preferred_levels] = await _list_daily_candidates(
                session,
                preferred_levels=preferred_levels,
            )
        return candidates_cache[preferred_levels]

    selected_question_ids: list[str] = []
    used_source_files: set[str] = set()
    used_categories: set[str] = set()
    for position in range(1, DAILY_CHALLENGE_TOTAL_QUESTIONS + 1):
        seed = _daily_selection_seed(berlin_date=berlin_date, position=position)
        candidate_pools = [
            pool
            for levels in _daily_level_windows_for_position(position)
            if (pool := await _cached_candidates(levels))
        ]
        if not candidate_pools:
            break

        selected = _select_daily_candidate(
            candidate_pools,
            selected_question_ids=selected_question_ids,
            used_source_files=used_source_files,
            used_categories=used_categories,
            selection_seed=seed,
        )
        if selected is None:
            break
        selected_question_ids.append(selected.question_id)
        used_source_files.add(selected.source_file)
        used_categories.add(selected.category)
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
