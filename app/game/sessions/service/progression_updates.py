from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.mode_progress import ModeProgress
from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.mode_progress_repo import ModeProgressRepo

from .progression_config import (
    LEVEL_CHAIN,
    MAX_MIX_STEP,
    _mode_progression_config,
    _next_chain_level,
    _normalize_chain_level,
)


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


async def get_rolling_accuracy(user_id: int, mode: str, db: AsyncSession) -> float:
    mode_config = _mode_progression_config(mode)
    recent_results = await _recent_attempt_results(
        db,
        user_id=user_id,
        mode=mode,
        limit=mode_config.warm_up_threshold,
    )
    if not recent_results:
        return 0.0
    correct_answers = sum(1 for answer in recent_results if answer)
    return correct_answers / len(recent_results)


async def _load_or_initialize_progress(
    db: AsyncSession,
    *,
    user_id: int,
    mode: str,
    now_utc: datetime,
) -> ModeProgress:
    progress = await ModeProgressRepo.get_by_user_mode_for_update(
        db,
        user_id=user_id,
        mode_code=mode,
    )
    if progress is not None:
        return progress
    return await ModeProgressRepo.upsert_preferred_level(
        db,
        user_id=user_id,
        mode_code=mode,
        preferred_level=LEVEL_CHAIN[0],
        now_utc=now_utc,
    )


async def _reset_terminal_mix_state(
    db: AsyncSession,
    *,
    progress: ModeProgress,
    current_level: str,
    now_utc: datetime,
) -> tuple[str, int, int]:
    if progress.mix_step != 0 or progress.correct_in_mix != 0:
        progress.mix_step = 0
        progress.correct_in_mix = 0
        progress.updated_at = now_utc
        await db.flush()
    return (current_level, progress.mix_step, progress.correct_in_mix)


async def _maybe_activate_mix_step(
    db: AsyncSession,
    *,
    progress: ModeProgress,
    current_level: str,
    recent_results: list[bool],
    mode: str,
    user_id: int,
    now_utc: datetime,
) -> tuple[str, int, int]:
    mode_config = _mode_progression_config(mode)
    if len(recent_results) < mode_config.warm_up_threshold:
        return (current_level, 0, 0)

    accuracy = await get_rolling_accuracy(user_id, mode, db)
    if accuracy >= mode_config.accuracy_threshold:
        progress.mix_step = 1
        progress.correct_in_mix = 0
        progress.updated_at = now_utc
        await db.flush()
    return (current_level, progress.mix_step, progress.correct_in_mix)


def _apply_correct_mixed_answer(
    *,
    progress: ModeProgress,
    current_level: str,
    next_level: str,
    correct_per_step: int,
) -> tuple[str, int, int]:
    progress.correct_in_mix += 1
    if progress.correct_in_mix < correct_per_step:
        return (current_level, progress.mix_step, progress.correct_in_mix)

    next_step = progress.mix_step + 1
    if next_step <= MAX_MIX_STEP:
        progress.mix_step = next_step
        progress.correct_in_mix = 0
        return (current_level, progress.mix_step, progress.correct_in_mix)

    progress.preferred_level = next_level
    progress.mix_step = 0
    progress.correct_in_mix = 0
    return (next_level, progress.mix_step, progress.correct_in_mix)


async def check_and_advance(
    user_id: int,
    mode: str,
    db: AsyncSession,
    *,
    now_utc: datetime | None = None,
) -> tuple[str, int, int]:
    effective_now = now_utc or datetime.now(timezone.utc)
    progress = await _load_or_initialize_progress(
        db,
        user_id=user_id,
        mode=mode,
        now_utc=effective_now,
    )

    current_level = _normalize_chain_level(progress.preferred_level)
    if current_level != progress.preferred_level:
        progress.preferred_level = current_level
    next_level = _next_chain_level(current_level)
    if next_level is None:
        return await _reset_terminal_mix_state(
            db,
            progress=progress,
            current_level=current_level,
            now_utc=effective_now,
        )

    mode_config = _mode_progression_config(mode)
    recent_results = await _recent_attempt_results(
        db,
        user_id=user_id,
        mode=mode,
        limit=mode_config.warm_up_threshold,
    )

    if progress.mix_step <= 0:
        return await _maybe_activate_mix_step(
            db,
            progress=progress,
            current_level=current_level,
            recent_results=recent_results,
            mode=mode,
            user_id=user_id,
            now_utc=effective_now,
        )

    if not (recent_results[0] if recent_results else False):
        return (current_level, progress.mix_step, progress.correct_in_mix)

    progress.updated_at = effective_now
    current_level, mix_step, correct_in_mix = _apply_correct_mixed_answer(
        progress=progress,
        current_level=current_level,
        next_level=next_level,
        correct_per_step=mode_config.correct_per_step,
    )
    await db.flush()
    return (current_level, mix_step, correct_in_mix)
