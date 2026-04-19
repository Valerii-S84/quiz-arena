from __future__ import annotations

from datetime import datetime, timezone

import structlog

from app.core.analytics_events import EVENT_SOURCE_WORKER, emit_analytics_event
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.session import SessionLocal
from app.game.sessions.service.friend_challenges_expiry import _expire_friend_challenge_if_due
from app.workers.tasks.friend_challenges_async_notifications import (
    send_deadline_notifications_with_events,
)
from app.workers.tasks.friend_challenges_async_processing import collect_deadline_items
from app.workers.tasks.friend_challenges_config import DEADLINE_BATCH_SIZE
from app.workers.tasks.friend_challenges_deadline_payloads import (
    ExpiredItem,
    deadline_result,
    duel_expired_payload,
    resolved_deadline_batch_size,
)
from app.workers.tasks.friend_challenges_notifications import send_deadline_notifications

logger = structlog.get_logger("app.workers.tasks.friend_challenges")


async def _emit_duel_expired_event(
    session,
    *,
    now_utc: datetime,
    expired_item: ExpiredItem,
) -> None:
    await emit_analytics_event(
        session,
        event_type="duel_expired",
        source=EVENT_SOURCE_WORKER,
        happened_at=now_utc,
        user_id=None,
        payload=duel_expired_payload(expired_item=expired_item),
    )


async def run_friend_challenge_deadlines_async(
    *, batch_size: int = DEADLINE_BATCH_SIZE
) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    resolved_batch_size = resolved_deadline_batch_size(batch_size=batch_size)
    reminder_items, expired_items = await collect_deadline_items(
        now_utc=now_utc,
        batch_size=resolved_batch_size,
        session_local=SessionLocal,
        repo=FriendChallengesRepo,
        expire_friend_challenge_if_due=_expire_friend_challenge_if_due,
        emit_duel_expired_event=lambda *, session, expired_item: _emit_duel_expired_event(
            session,
            now_utc=now_utc,
            expired_item=expired_item,
        ),
    )
    (
        reminders_sent,
        reminders_failed,
        expired_notices_sent,
        expired_notices_failed,
    ) = await send_deadline_notifications_with_events(
        now_utc=now_utc,
        reminder_items=reminder_items,
        expired_items=expired_items,
        send_deadline_notifications=send_deadline_notifications,
        session_local=SessionLocal,
        emit_analytics_event=emit_analytics_event,
        event_source_worker=EVENT_SOURCE_WORKER,
    )

    result = deadline_result(
        batch_size=resolved_batch_size,
        reminder_items=reminder_items,
        expired_items=expired_items,
        reminders_sent=reminders_sent,
        reminders_failed=reminders_failed,
        expired_notices_sent=expired_notices_sent,
        expired_notices_failed=expired_notices_failed,
    )
    logger.info("friend_challenge_deadlines_processed", **result)
    return result
