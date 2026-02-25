from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.mode_progress_repo import ModeProgressRepo
from app.game.questions.runtime_bank_models import QUICK_MIX_MODE_CODE

from .levels import _clamp_level_for_mode, _is_persistent_adaptive_mode
from .question_loading import _infer_preferred_level_from_recent_attempt


async def resolve_effective_preferred_level(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    preferred_question_level: str | None,
    now_utc: datetime,
) -> str | None:
    effective_preferred_level = preferred_question_level
    if effective_preferred_level is None and mode_code == QUICK_MIX_MODE_CODE and source == "MENU":
        effective_preferred_level = "A1"

    if not _is_persistent_adaptive_mode(mode_code=mode_code):
        return effective_preferred_level

    mode_progress = None
    if effective_preferred_level is None:
        mode_progress = await ModeProgressRepo.get_by_user_mode(
            session,
            user_id=user_id,
            mode_code=mode_code,
        )
        if mode_progress is not None:
            effective_preferred_level = mode_progress.preferred_level
        else:
            effective_preferred_level = await _infer_preferred_level_from_recent_attempt(
                session,
                user_id=user_id,
                mode_code=mode_code,
            )

    if mode_progress is None and effective_preferred_level is not None:
        seeded_level = _clamp_level_for_mode(
            mode_code=mode_code,
            level=effective_preferred_level,
        )
        if seeded_level is not None:
            await ModeProgressRepo.upsert_preferred_level(
                session,
                user_id=user_id,
                mode_code=mode_code,
                preferred_level=seeded_level,
                now_utc=now_utc,
            )
            effective_preferred_level = seeded_level

    return _clamp_level_for_mode(
        mode_code=mode_code,
        level=effective_preferred_level,
    )
