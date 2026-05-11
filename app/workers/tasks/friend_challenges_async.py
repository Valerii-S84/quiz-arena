from __future__ import annotations

import structlog

from app.core.analytics_events import emit_analytics_event
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.session import SessionLocal
from app.workers.tasks.friend_challenges_config import DEADLINE_BATCH_SIZE
from app.workers.tasks.friend_challenges_deadline_flow import (
    build_deadline_context,
    collect_deadline_work,
    emit_notification_events,
    send_deadline_notifications_for_work,
)
from app.workers.tasks.friend_challenges_deadline_types import build_deadline_result
from app.workers.tasks.friend_challenges_notifications import send_deadline_notifications

logger = structlog.get_logger("app.workers.tasks.friend_challenges")


async def run_friend_challenge_deadlines_async(
    *, batch_size: int = DEADLINE_BATCH_SIZE
) -> dict[str, int]:
    context = build_deadline_context(batch_size=batch_size)

    async with SessionLocal.begin() as session:
        work = await collect_deadline_work(
            session,
            context=context,
            challenges_repo=FriendChallengesRepo,
            emit_event=emit_analytics_event,
        )

    notification_result = await send_deadline_notifications_for_work(
        context=context,
        work=work,
        send_notifications=send_deadline_notifications,
    )
    await emit_notification_events(
        context=context,
        notification_result=notification_result,
        session_factory=SessionLocal,
        emit_event=emit_analytics_event,
    )

    result = build_deadline_result(
        context=context,
        work=work,
        notification_result=notification_result,
    )
    logger.info("friend_challenge_deadlines_processed", **result)
    return result
