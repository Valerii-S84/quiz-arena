from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.mode_progress import ModeProgress
from app.db.repo.mode_progress_repo import ModeProgressRepo

from .progression_config import LEVEL_CHAIN, MAX_MIX_STEP, _mode_progression_config


async def load_or_initialize_progress(
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


async def reset_terminal_mix_state(
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


async def maybe_activate_mix_step(
    db: AsyncSession,
    *,
    progress: ModeProgress,
    current_level: str,
    recent_results: list[bool],
    mode: str,
    user_id: int,
    now_utc: datetime,
    get_rolling_accuracy_fn,
) -> tuple[str, int, int]:
    mode_config = _mode_progression_config(mode)
    if len(recent_results) < mode_config.warm_up_threshold:
        return (current_level, 0, 0)

    accuracy = await get_rolling_accuracy_fn(user_id, mode, db)
    if accuracy >= mode_config.accuracy_threshold:
        progress.mix_step = 1
        progress.correct_in_mix = 0
        progress.updated_at = now_utc
        await db.flush()
    return (current_level, progress.mix_step, progress.correct_in_mix)


def apply_correct_mixed_answer(
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


__all__ = [
    "apply_correct_mixed_answer",
    "load_or_initialize_progress",
    "maybe_activate_mix_step",
    "reset_terminal_mix_state",
]
