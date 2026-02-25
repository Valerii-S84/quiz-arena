from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.mode_progress_repo import ModeProgressRepo

from .levels import _clamp_level_for_mode
from .question_loading import _infer_preferred_level_from_recent_attempt

LEVEL_CHAIN: tuple[str, ...] = ("A1", "A2", "B1", "B2")
ROLLING_WINDOW_SIZE = 30
ROLLING_ACCURACY_THRESHOLD = 0.75
MIX_CORRECT_STEP_SIZE = 10
MIX_STEPS_WITH_WEIGHTS: dict[int, float] = {
    1: 0.25,
    2: 0.50,
    3: 0.75,
}


def _normalize_chain_level(level: str | None) -> str:
    if level is None:
        return LEVEL_CHAIN[0]
    normalized = level.strip().upper()
    if normalized not in LEVEL_CHAIN:
        return LEVEL_CHAIN[0]
    return normalized


def _next_chain_level(level: str) -> str | None:
    current_index = LEVEL_CHAIN.index(level)
    if current_index >= len(LEVEL_CHAIN) - 1:
        return None
    return LEVEL_CHAIN[current_index + 1]


async def _recent_attempt_results(
    db: AsyncSession,
    *,
    user_id: int,
    mode: str,
    limit: int,
) -> list[bool]:
    stmt = (
        select(QuizAttempt.is_correct)
        .join(QuizSession, QuizAttempt.session_id == QuizSession.id)
        .where(
            QuizAttempt.user_id == user_id,
            QuizSession.mode_code == mode,
        )
        .order_by(QuizAttempt.answered_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [bool(value) for value in result.scalars().all()]


def get_allowed_levels(current_level: str, mix_step: int = 0) -> tuple[str, ...]:
    normalized = _normalize_chain_level(current_level)
    next_level = _next_chain_level(normalized)
    if mix_step <= 0 or next_level is None:
        return (normalized,)
    return (normalized, next_level)


async def get_rolling_accuracy(user_id: int, mode: str, db: AsyncSession) -> float:
    recent_results = await _recent_attempt_results(
        db,
        user_id=user_id,
        mode=mode,
        limit=ROLLING_WINDOW_SIZE,
    )
    if not recent_results:
        return 0.0
    correct_answers = sum(1 for answer in recent_results if answer)
    return correct_answers / len(recent_results)


async def check_and_advance(
    user_id: int,
    mode: str,
    db: AsyncSession,
    *,
    now_utc: datetime | None = None,
) -> tuple[str, int, int]:
    effective_now = now_utc or datetime.now(timezone.utc)
    progress = await ModeProgressRepo.get_by_user_mode_for_update(
        db,
        user_id=user_id,
        mode_code=mode,
    )

    if progress is None:
        progress = await ModeProgressRepo.upsert_preferred_level(
            db,
            user_id=user_id,
            mode_code=mode,
            preferred_level=LEVEL_CHAIN[0],
            now_utc=effective_now,
        )

    current_level = _normalize_chain_level(progress.preferred_level)
    if current_level != progress.preferred_level:
        progress.preferred_level = current_level

    # Last persisted step is relevant only while a next level exists.
    next_level = _next_chain_level(current_level)
    if next_level is None:
        if progress.mix_step != 0 or progress.correct_in_mix != 0:
            progress.mix_step = 0
            progress.correct_in_mix = 0
            progress.updated_at = effective_now
            await db.flush()
        return (current_level, progress.mix_step, progress.correct_in_mix)

    recent_results = await _recent_attempt_results(
        db,
        user_id=user_id,
        mode=mode,
        limit=ROLLING_WINDOW_SIZE,
    )

    if progress.mix_step <= 0:
        if len(recent_results) < ROLLING_WINDOW_SIZE:
            return (current_level, 0, 0)
        accuracy = await get_rolling_accuracy(user_id, mode, db)
        if accuracy >= ROLLING_ACCURACY_THRESHOLD:
            progress.mix_step = 1
            progress.correct_in_mix = 0
            progress.updated_at = effective_now
            await db.flush()
        return (current_level, progress.mix_step, progress.correct_in_mix)

    current_answer_correct = recent_results[0] if recent_results else False
    if not current_answer_correct:
        return (current_level, progress.mix_step, progress.correct_in_mix)

    progress.correct_in_mix += 1
    progress.updated_at = effective_now

    if progress.correct_in_mix >= MIX_CORRECT_STEP_SIZE:
        if progress.mix_step < max(MIX_STEPS_WITH_WEIGHTS):
            progress.mix_step += 1
            progress.correct_in_mix = 0
        else:
            progress.preferred_level = next_level
            progress.mix_step = 0
            progress.correct_in_mix = 0
            current_level = next_level

    await db.flush()
    return (current_level, progress.mix_step, progress.correct_in_mix)


def select_level_weighted(
    current_level: str,
    mix_step: int,
    *,
    selection_seed: str,
) -> str:
    normalized = _normalize_chain_level(current_level)
    next_level = _next_chain_level(normalized)
    if next_level is None:
        return normalized

    next_weight = MIX_STEPS_WITH_WEIGHTS.get(mix_step, 0.0)
    if next_weight <= 0:
        return normalized

    digest = hashlib.sha256(selection_seed.encode("utf-8")).digest()
    roll = int.from_bytes(digest[:8], "big") / 2**64
    return next_level if roll < next_weight else normalized


async def resolve_start_progression_state(
    db: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    preferred_level_override: str | None,
    now_utc: datetime,
) -> tuple[str, int, tuple[str, ...]]:
    effective_level = preferred_level_override
    mix_step = 0
    mode_progress = await ModeProgressRepo.get_by_user_mode(
        db,
        user_id=user_id,
        mode_code=mode_code,
    )
    if effective_level is None:
        if mode_progress is not None:
            effective_level = mode_progress.preferred_level
            mix_step = mode_progress.mix_step
        else:
            effective_level = await _infer_preferred_level_from_recent_attempt(
                db,
                user_id=user_id,
                mode_code=mode_code,
            )
    effective_level = (
        _clamp_level_for_mode(mode_code=mode_code, level=effective_level) or LEVEL_CHAIN[0]
    )

    if mode_progress is None:
        mode_progress = await ModeProgressRepo.upsert_preferred_level(
            db,
            user_id=user_id,
            mode_code=mode_code,
            preferred_level=effective_level,
            now_utc=now_utc,
        )
        mix_step = mode_progress.mix_step
        effective_level = mode_progress.preferred_level

    allowed_levels = get_allowed_levels(effective_level, mix_step)
    return (effective_level, mix_step, allowed_levels)
