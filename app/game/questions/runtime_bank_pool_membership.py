from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.db.repo.quiz_questions_repo import QuizQuestionPoolCandidate, QuizQuestionPoolChange
from app.game.questions.runtime_bank_models import QUICK_MIX_MODE_CODE, QUICK_MIX_SCOPE_CODE
from app.game.questions.types import QuizQuestion


@dataclass(frozen=True, slots=True)
class PoolRefreshResult:
    question_ids: tuple[str, ...]
    candidates_by_id: dict[str, QuizQuestionPoolCandidate]
    updated_at_watermark: datetime
    invalidated_question_ids: tuple[str, ...]


def pool_cache_scope(mode_code: str) -> str:
    return QUICK_MIX_SCOPE_CODE if mode_code == QUICK_MIX_MODE_CODE else mode_code


def question_from_pool_candidate(candidate: QuizQuestionPoolCandidate) -> QuizQuestion | None:
    if (
        candidate.question_text is None
        or candidate.option_1 is None
        or candidate.option_2 is None
        or candidate.option_3 is None
        or candidate.option_4 is None
        or candidate.correct_option_id is None
    ):
        return None
    return QuizQuestion(
        question_id=candidate.question_id,
        text=candidate.question_text,
        options=(
            candidate.option_1,
            candidate.option_2,
            candidate.option_3,
            candidate.option_4,
        ),
        correct_option=candidate.correct_option_id,
        level=candidate.level,
        category=candidate.category,
    )


def _pool_matches_mode(
    mode_code: str,
    *,
    question_mode_code: str,
    question_quick_mix_eligible: bool,
) -> bool:
    if mode_code == QUICK_MIX_MODE_CODE:
        return question_quick_mix_eligible
    return question_mode_code == mode_code


def _pool_matches_level(
    preferred_levels: tuple[str, ...] | None,
    *,
    question_level: str,
) -> bool:
    return preferred_levels is None or question_level in preferred_levels


def _pool_includes_question(
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
    *,
    question_mode_code: str,
    question_level: str,
    question_status: str,
    question_quick_mix_eligible: bool,
) -> bool:
    return (
        question_status == "ACTIVE"
        and _pool_matches_mode(
            mode_code,
            question_mode_code=question_mode_code,
            question_quick_mix_eligible=question_quick_mix_eligible,
        )
        and _pool_matches_level(preferred_levels, question_level=question_level)
    )


def refresh_pool_candidates(
    changes: Sequence[QuizQuestionPoolChange],
    *,
    mode_code: str,
    preferred_levels: tuple[str, ...] | None,
    cached_candidates_by_id: dict[str, QuizQuestionPoolCandidate],
    cached_updated_at_watermark: datetime,
) -> PoolRefreshResult:
    refreshed_candidates = dict(cached_candidates_by_id)
    max_updated_at = cached_updated_at_watermark
    invalidated_question_ids: list[str] = []
    for change in changes:
        invalidated_question_ids.append(change.question_id)
        if _pool_includes_question(
            mode_code,
            preferred_levels,
            question_mode_code=change.mode_code,
            question_level=change.level,
            question_status=change.status,
            question_quick_mix_eligible=change.quick_mix_eligible,
        ):
            refreshed_candidates[change.question_id] = _candidate_from_change(change)
        else:
            refreshed_candidates.pop(change.question_id, None)
        if change.updated_at > max_updated_at:
            max_updated_at = change.updated_at

    refreshed_ids = tuple(sorted(refreshed_candidates))
    return PoolRefreshResult(
        question_ids=refreshed_ids,
        candidates_by_id={
            question_id: refreshed_candidates[question_id] for question_id in refreshed_ids
        },
        updated_at_watermark=max_updated_at,
        invalidated_question_ids=tuple(invalidated_question_ids),
    )


def _candidate_from_change(change: QuizQuestionPoolChange) -> QuizQuestionPoolCandidate:
    return QuizQuestionPoolCandidate(
        question_id=change.question_id,
        level=change.level,
        source_file=getattr(change, "source_file", ""),
        category=getattr(change, "category", ""),
        question_text=getattr(change, "question_text", None),
        option_1=getattr(change, "option_1", None),
        option_2=getattr(change, "option_2", None),
        option_3=getattr(change, "option_3", None),
        option_4=getattr(change, "option_4", None),
        correct_option_id=getattr(change, "correct_option_id", None),
    )
