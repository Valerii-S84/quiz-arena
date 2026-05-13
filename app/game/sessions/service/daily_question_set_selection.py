from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

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


async def build_daily_question_ids(
    session: AsyncSession,
    *,
    berlin_date: date,
) -> tuple[str, ...]:
    candidates_cache: dict[tuple[str, ...], list[QuizQuestionPoolCandidate]] = {}
    selected_question_ids: list[str] = []
    used_source_files: set[str] = set()
    used_categories: set[str] = set()

    for position in range(1, DAILY_CHALLENGE_TOTAL_QUESTIONS + 1):
        candidate_pools = await _candidate_pools_for_position(
            session,
            position=position,
            candidates_cache=candidates_cache,
        )
        if not candidate_pools:
            break
        selected = _select_daily_candidate(
            candidate_pools,
            selected_question_ids=selected_question_ids,
            used_source_files=used_source_files,
            used_categories=used_categories,
            selection_seed=_daily_selection_seed(berlin_date=berlin_date, position=position),
        )
        if selected is None:
            break
        selected_question_ids.append(selected.question_id)
        used_source_files.add(selected.source_file)
        used_categories.add(selected.category)
    return tuple(selected_question_ids)


def _daily_selection_seed(*, berlin_date: date, position: int) -> str:
    return f"daily:{berlin_date.isoformat()}:{DAILY_CHALLENGE_SOURCE_MODE}:{position}"


def _daily_level_windows_for_position(position: int) -> tuple[tuple[str, ...], ...]:
    preferred_level, allowed_levels = daily_level_window_for_position(position)
    level_windows = ((preferred_level,), allowed_levels, DAILY_LEVEL_CHAIN)
    ordered_unique: list[tuple[str, ...]] = []
    for levels in level_windows:
        if levels not in ordered_unique:
            ordered_unique.append(levels)
    return tuple(ordered_unique)


async def _candidate_pools_for_position(
    session: AsyncSession,
    *,
    position: int,
    candidates_cache: dict[tuple[str, ...], list[QuizQuestionPoolCandidate]],
) -> list[list[QuizQuestionPoolCandidate]]:
    return [
        pool
        for levels in _daily_level_windows_for_position(position)
        if (pool := await _cached_candidates(session, levels, candidates_cache))
    ]


async def _cached_candidates(
    session: AsyncSession,
    preferred_levels: tuple[str, ...],
    candidates_cache: dict[tuple[str, ...], list[QuizQuestionPoolCandidate]],
) -> list[QuizQuestionPoolCandidate]:
    if preferred_levels not in candidates_cache:
        candidates_cache[preferred_levels] = await _list_daily_candidates(
            session,
            preferred_levels=preferred_levels,
        )
    return candidates_cache[preferred_levels]


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


def _select_daily_candidate(
    candidate_pools: Sequence[Sequence[QuizQuestionPoolCandidate]],
    *,
    selected_question_ids: Sequence[str],
    used_source_files: set[str],
    used_categories: set[str],
    selection_seed: str,
) -> QuizQuestionPoolCandidate | None:
    selected_ids = set(selected_question_ids)
    matchers: tuple[Callable[[QuizQuestionPoolCandidate], bool], ...] = (
        lambda candidate: (
            candidate.question_id not in selected_ids
            and candidate.source_file not in used_source_files
        ),
        lambda candidate: (
            candidate.question_id not in selected_ids and candidate.category not in used_categories
        ),
        lambda candidate: candidate.question_id not in selected_ids,
        lambda candidate: True,
    )
    for matches in matchers:
        selected = _pick_from_daily_candidate_pools(
            candidate_pools,
            matches=matches,
            selection_seed=selection_seed,
        )
        if selected is not None:
            return selected
    return None


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


def _pick_daily_candidate(
    candidates: Sequence[QuizQuestionPoolCandidate],
    *,
    selection_seed: str,
) -> QuizQuestionPoolCandidate | None:
    if not candidates:
        return None
    ordered = sorted(candidates, key=lambda candidate: candidate.question_id)
    return ordered[stable_index(selection_seed, len(ordered))]
