from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.mode_progress import ModeProgress
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


@dataclass(frozen=True, slots=True)
class _StartProgressionState:
    effective_level: str
    mix_step: int


def _normalize_start_level(*, mode_code: str, level: str | None) -> str:
    return _clamp_level_for_mode(mode_code=mode_code, level=level) or LEVEL_CHAIN[0]


async def _resolve_requested_start_state(
    db: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    preferred_level_override: str | None,
    mode_progress: ModeProgress | None,
) -> _StartProgressionState:
    if preferred_level_override is not None:
        return _StartProgressionState(
            effective_level=_normalize_start_level(
                mode_code=mode_code,
                level=preferred_level_override,
            ),
            mix_step=0,
        )
    if mode_progress is not None:
        return _StartProgressionState(
            effective_level=_normalize_start_level(
                mode_code=mode_code,
                level=mode_progress.preferred_level,
            ),
            mix_step=mode_progress.mix_step,
        )

    inferred_level = await _infer_preferred_level_from_recent_attempt(
        db,
        user_id=user_id,
        mode_code=mode_code,
    )
    return _StartProgressionState(
        effective_level=_normalize_start_level(mode_code=mode_code, level=inferred_level),
        mix_step=0,
    )


async def _persist_missing_start_state(
    db: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    now_utc: datetime,
    mode_progress: ModeProgress | None,
    state: _StartProgressionState,
) -> _StartProgressionState:
    if mode_progress is not None:
        return state

    persisted_progress = await ModeProgressRepo.upsert_preferred_level(
        db,
        user_id=user_id,
        mode_code=mode_code,
        preferred_level=state.effective_level,
        now_utc=now_utc,
    )
    return _StartProgressionState(
        effective_level=persisted_progress.preferred_level,
        mix_step=persisted_progress.mix_step,
    )


async def resolve_start_progression_state(
    db: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    preferred_level_override: str | None,
    now_utc: datetime,
) -> tuple[str, int, tuple[str, ...]]:
    mode_progress = await ModeProgressRepo.get_by_user_mode(
        db,
        user_id=user_id,
        mode_code=mode_code,
    )
    state = await _resolve_requested_start_state(
        db,
        user_id=user_id,
        mode_code=mode_code,
        preferred_level_override=preferred_level_override,
        mode_progress=mode_progress,
    )
    state = await _persist_missing_start_state(
        db,
        user_id=user_id,
        mode_code=mode_code,
        now_utc=now_utc,
        mode_progress=mode_progress,
        state=state,
    )
    allowed_levels = get_allowed_levels(state.effective_level, state.mix_step)
    return (state.effective_level, state.mix_step, allowed_levels)
