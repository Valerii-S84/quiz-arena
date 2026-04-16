from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.mode_progress_repo import ModeProgressRepo

from .levels import _clamp_level_for_mode
from .progression_config import LEVEL_CHAIN, get_allowed_levels, select_level_weighted
from .progression_updates import check_and_advance
from .question_loading import _infer_preferred_level_from_recent_attempt

__all__ = [
    "check_and_advance",
    "get_allowed_levels",
    "resolve_start_progression_state",
    "select_level_weighted",
]


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
