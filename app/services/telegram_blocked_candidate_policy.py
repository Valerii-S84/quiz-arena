from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.production_reliability_types import TelegramDeliveryAttemptCreate
from app.services.telegram_delivery_outcomes import TelegramDeliverySkip

BLOCKED_CANDIDATE_TTL = timedelta(days=30)
BLOCKED_CANDIDATE_FAILURE_CODE = "TELEGRAM_BLOCKED_CANDIDATE"
BLOCKED_CANDIDATE_FAILURE_REASON = "known blocked candidate"


async def blocked_candidate_skip(
    session: AsyncSession,
    *,
    attempt: TelegramDeliveryAttemptCreate,
    attempts_repo: Any,
) -> TelegramDeliverySkip | None:
    telegram_user_id = attempt.telegram_user_id
    has_blocked_candidate = getattr(attempts_repo, "has_blocked_candidate", None)
    if telegram_user_id is None or not callable(has_blocked_candidate):
        return None
    if not await has_blocked_candidate(
        session,
        telegram_user_id=telegram_user_id,
        blocked_since=datetime.now(UTC) - BLOCKED_CANDIDATE_TTL,
    ):
        return None
    return TelegramDeliverySkip(
        failure_code=BLOCKED_CANDIDATE_FAILURE_CODE,
        failure_reason=BLOCKED_CANDIDATE_FAILURE_REASON,
    )


__all__ = [
    "BLOCKED_CANDIDATE_FAILURE_CODE",
    "BLOCKED_CANDIDATE_FAILURE_REASON",
    "BLOCKED_CANDIDATE_TTL",
    "blocked_candidate_skip",
]
