from __future__ import annotations

import hashlib
from datetime import date
from typing import Sequence

from app.game.questions.static_bank_artikel_pool import build_artikel_sprint_pool
from app.game.questions.static_bank_quick_mix_pool import build_quick_mix_pool
from app.game.questions.types import QuizQuestion


def _daily_challenge_question(local_date_berlin: date) -> QuizQuestion:
    question_id = f"dc_{local_date_berlin.isoformat()}"
    return QuizQuestion(
        question_id=question_id,
        text="Daily Challenge: Was ist der richtige Artikel für 'Tisch'?",
        options=("das", "die", "der", "den"),
        correct_option=2,
    )


_QUICK_MIX_A1A2_POOL: tuple[QuizQuestion, ...] = build_quick_mix_pool()
_ARTIKEL_SPRINT_POOL: tuple[QuizQuestion, ...] = build_artikel_sprint_pool()


_GENERIC_POOL: tuple[QuizQuestion, ...] = (
    QuizQuestion(
        question_id="generic_001",
        text="Wähle die korrekte Antwort:",
        options=("Antwort A", "Antwort B", "Antwort C", "Antwort D"),
        correct_option=0,
    ),
    QuizQuestion(
        question_id="generic_002",
        text="Wähle die beste Option:",
        options=("Option 1", "Option 2", "Option 3", "Option 4"),
        correct_option=1,
    ),
)


def _question_pool_for_mode(mode_code: str) -> tuple[QuizQuestion, ...]:
    if mode_code == "QUICK_MIX_A1A2":
        return _QUICK_MIX_A1A2_POOL
    if mode_code == "ARTIKEL_SPRINT":
        return _ARTIKEL_SPRINT_POOL
    return _GENERIC_POOL


def _stable_index(seed: str, size: int) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % size


def get_question_by_id(
    mode_code: str,
    *,
    question_id: str,
    local_date_berlin: date,
) -> QuizQuestion | None:
    if mode_code == "DAILY_CHALLENGE":
        question = _daily_challenge_question(local_date_berlin)
        return question if question.question_id == question_id else None

    for question in _question_pool_for_mode(mode_code):
        if question.question_id == question_id:
            return question
    return None


def select_question_for_mode(
    mode_code: str,
    *,
    local_date_berlin: date,
    recent_question_ids: Sequence[str],
    selection_seed: str,
    preferred_level: str | None = None,
    allowed_levels: Sequence[str] | None = None,
) -> QuizQuestion:
    if mode_code == "DAILY_CHALLENGE":
        return _daily_challenge_question(local_date_berlin)

    normalized_preferred = preferred_level.strip().upper() if preferred_level else None
    normalized_allowed_levels = (
        tuple(dict.fromkeys(level.strip().upper() for level in allowed_levels if level))
        if allowed_levels
        else None
    )
    primary_levels = (
        (normalized_preferred,) if normalized_preferred is not None else normalized_allowed_levels
    )

    pool = _question_pool_for_mode(mode_code)
    recent_ids_set = set(recent_question_ids)
    candidates = [
        question
        for question in pool
        if question.question_id not in recent_ids_set
        and (primary_levels is None or question.level in primary_levels)
    ]
    if (
        not candidates
        and normalized_preferred is not None
        and normalized_allowed_levels is not None
    ):
        candidates = [
            question
            for question in pool
            if question.question_id not in recent_ids_set
            and question.level in normalized_allowed_levels
        ]
    if not candidates:
        candidates = [
            question
            for question in pool
            if primary_levels is None or question.level in primary_levels
        ]
    if (
        not candidates
        and normalized_preferred is not None
        and normalized_allowed_levels is not None
    ):
        candidates = [question for question in pool if question.level in normalized_allowed_levels]
    if not candidates:
        raise LookupError(
            f"No fallback questions available for mode={mode_code} levels={primary_levels}"
        )

    index = _stable_index(selection_seed, len(candidates))
    return candidates[index]


def get_question_for_mode(mode_code: str, *, local_date_berlin: date) -> QuizQuestion:
    if mode_code == "DAILY_CHALLENGE":
        return _daily_challenge_question(local_date_berlin)

    return _question_pool_for_mode(mode_code)[0]
