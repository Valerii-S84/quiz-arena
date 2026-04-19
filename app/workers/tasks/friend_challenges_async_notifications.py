from __future__ import annotations

from datetime import datetime
from typing import cast

from app.workers.tasks.friend_challenges_deadline_payloads import ExpiredItem, ReminderItem


async def emit_deadline_notification_events(
    *,
    now_utc: datetime,
    reminder_events: list[dict[str, object]],
    expired_notice_events: list[dict[str, object]],
    session_local,
    emit_analytics_event,
    event_source_worker: str,
) -> None:
    if not reminder_events and not expired_notice_events:
        return
    async with session_local.begin() as session:
        for payload in reminder_events:
            await emit_analytics_event(
                session,
                event_type="friend_challenge_last_chance_sent",
                source=event_source_worker,
                happened_at=now_utc,
                user_id=None,
                payload=payload,
            )
        for payload in expired_notice_events:
            await emit_analytics_event(
                session,
                event_type="friend_challenge_expired_notice_sent",
                source=event_source_worker,
                happened_at=now_utc,
                user_id=None,
                payload=payload,
            )


async def send_deadline_notifications_with_events(
    *,
    now_utc: datetime,
    reminder_items: list[ReminderItem],
    expired_items: list[ExpiredItem],
    send_deadline_notifications,
    session_local,
    emit_analytics_event,
    event_source_worker: str,
) -> tuple[int, int, int, int]:
    (
        reminders_sent,
        reminders_failed,
        expired_notices_sent,
        expired_notices_failed,
        reminder_events,
        expired_notice_events,
    ) = await send_deadline_notifications(
        now_utc=now_utc,
        reminder_items=cast(list[dict[str, object]], reminder_items),
        expired_items=cast(list[dict[str, object]], expired_items),
    )
    await emit_deadline_notification_events(
        now_utc=now_utc,
        reminder_events=reminder_events,
        expired_notice_events=expired_notice_events,
        session_local=session_local,
        emit_analytics_event=emit_analytics_event,
        event_source_worker=event_source_worker,
    )
    return (
        reminders_sent,
        reminders_failed,
        expired_notices_sent,
        expired_notices_failed,
    )
