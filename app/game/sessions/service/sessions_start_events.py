from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.repo.users_repo import UsersRepo
from app.services.alerts import send_ops_alert

_EVENT_QUESTION_MODE_MISMATCH = "question_mode_mismatch"
_EVENT_QUESTION_LEVEL_SERVED = "question_level_served"
_ALERT_QUESTION_MODE_MISMATCH = "gameplay_question_mode_mismatch"
_ALERT_NEW_USER_HIGH_LEVEL = "gameplay_new_user_high_level_served"
_NEW_USER_MAX_AGE = timedelta(hours=24)
_NEW_USER_HIGH_LEVELS: frozenset[str] = frozenset({"B1", "B2"})


async def emit_question_mode_mismatch_event(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    expected_level: str | None,
    served_level: str | None,
    served_question_mode: str,
    question_id: str,
    fallback_step: str,
    retry_count: int,
    mismatch_reason: str,
    now_utc: datetime,
) -> None:
    payload: dict[str, object] = {
        "mode_code": mode_code,
        "source": source,
        "expected_level": expected_level,
        "served_level": served_level,
        "served_question_mode": served_question_mode,
        "question_id": question_id,
        "fallback_step": fallback_step,
        "retry_count": retry_count,
        "mismatch_reason": mismatch_reason,
    }
    await emit_analytics_event(
        session,
        event_type=_EVENT_QUESTION_MODE_MISMATCH,
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload=payload,
    )
    await send_ops_alert(
        event=_ALERT_QUESTION_MODE_MISMATCH,
        payload=payload,
    )


async def emit_question_level_served_event(
    session: AsyncSession,
    *,
    user_id: int,
    mode_code: str,
    source: str,
    expected_level: str | None,
    served_level: str | None,
    served_question_mode: str,
    question_id: str,
    fallback_step: str,
    retry_count: int,
    mismatch_reason: str,
    now_utc: datetime,
) -> None:
    if source != "MENU":
        return
    payload: dict[str, object] = {
        "mode_code": mode_code,
        "source": source,
        "expected_level": expected_level,
        "served_level": served_level,
        "served_question_mode": served_question_mode,
        "question_id": question_id,
        "fallback_step": fallback_step,
        "retry_count": retry_count,
        "mismatch_reason": mismatch_reason,
    }
    await emit_analytics_event(
        session,
        event_type=_EVENT_QUESTION_LEVEL_SERVED,
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload=payload,
    )
    if served_level not in _NEW_USER_HIGH_LEVELS:
        return
    user = await UsersRepo.get_by_id(session, user_id)
    if user is None or (now_utc - user.created_at) >= _NEW_USER_MAX_AGE:
        return
    await send_ops_alert(
        event=_ALERT_NEW_USER_HIGH_LEVEL,
        payload=payload,
    )
