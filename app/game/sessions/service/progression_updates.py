from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from .progression_config import _mode_progression_config, _next_chain_level, _normalize_chain_level
from .progression_mix_state import (
    apply_correct_mixed_answer,
    load_or_initialize_progress,
    maybe_activate_mix_step,
    reset_terminal_mix_state,
)
from .progression_recent_results import recent_attempt_results


async def get_rolling_accuracy(user_id: int, mode: str, db: AsyncSession) -> float:
    mode_config = _mode_progression_config(mode)
    recent_results = await recent_attempt_results(
        db,
        user_id=user_id,
        mode=mode,
        limit=mode_config.warm_up_threshold,
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
    progress = await load_or_initialize_progress(
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
        return await reset_terminal_mix_state(
            db,
            progress=progress,
            current_level=current_level,
            now_utc=effective_now,
        )

    mode_config = _mode_progression_config(mode)
    recent_results = await recent_attempt_results(
        db,
        user_id=user_id,
        mode=mode,
        limit=mode_config.warm_up_threshold,
    )

    if progress.mix_step <= 0:
        return await maybe_activate_mix_step(
            db,
            progress=progress,
            current_level=current_level,
            recent_results=recent_results,
            mode=mode,
            user_id=user_id,
            now_utc=effective_now,
            get_rolling_accuracy_fn=get_rolling_accuracy,
        )

    if not (recent_results[0] if recent_results else False):
        return (current_level, progress.mix_step, progress.correct_in_mix)

    progress.updated_at = effective_now
    current_level, mix_step, correct_in_mix = apply_correct_mixed_answer(
        progress=progress,
        current_level=current_level,
        next_level=next_level,
        correct_per_step=mode_config.correct_per_step,
    )
    await db.flush()
    return (current_level, mix_step, correct_in_mix)
