from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

import structlog

from app.core.analytics_events import EVENT_SOURCE_WORKER, emit_analytics_event
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.session import SessionLocal
from app.game.sessions.service.friend_challenges_expiry import _expire_friend_challenge_if_due
from app.workers.tasks.friend_challenges_config import DEADLINE_BATCH_SIZE
from app.workers.tasks.friend_challenges_deadline_payloads import (
    ExpiredItem,
    ReminderItem,
    deadline_result,
    duel_expired_payload,
    expired_item,
    expires_before_utc,
    last_chance_reminder_user_id,
    reminder_item,
    resolved_deadline_batch_size,
)
from app.workers.tasks.friend_challenges_notifications import send_deadline_notifications

logger = structlog.get_logger("app.workers.tasks.friend_challenges")


async def _queue_last_chance_reminders(
    session,
    *,
    now_utc: datetime,
    expires_before_utc: datetime,
    batch_size: int,
) -> list[ReminderItem]:
    reminder_items: list[ReminderItem] = []
    due_last_chance = await FriendChallengesRepo.list_active_due_for_last_chance_for_update(
        session,
        now_utc=now_utc,
        expires_before_utc=expires_before_utc,
        limit=batch_size,
    )
    for challenge in due_last_chance:
        reminder_user_id = last_chance_reminder_user_id(challenge=challenge)
        if reminder_user_id is None:
            continue
        challenge.expires_last_chance_notified_at = now_utc
        challenge.updated_at = now_utc
        reminder_items.append(
            reminder_item(
                challenge=challenge,
                reminder_user_id=reminder_user_id,
            )
        )
    return reminder_items


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


async def _collect_expired_items(
    session,
    *,
    now_utc: datetime,
    batch_size: int,
) -> list[ExpiredItem]:
    expired_items: list[ExpiredItem] = []
    pending_due = await FriendChallengesRepo.list_pending_due_for_expire_for_update(
        session,
        now_utc=now_utc,
        limit=batch_size,
    )
    joined_due = await FriendChallengesRepo.list_joined_due_for_walkover_for_update(
        session,
        now_utc=now_utc,
        limit=batch_size,
    )
    for challenge in [*pending_due, *joined_due]:
        previous_status = str(challenge.status)
        if not _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
            continue
        expired_notice = expired_item(
            challenge=challenge,
            previous_status=previous_status,
        )
        expired_items.append(expired_notice)
        await _emit_duel_expired_event(
            session,
            now_utc=now_utc,
            expired_item=expired_notice,
        )
    return expired_items


async def _collect_deadline_items(
    *,
    now_utc: datetime,
    batch_size: int,
) -> tuple[list[ReminderItem], list[ExpiredItem]]:
    async with SessionLocal.begin() as session:
        reminder_items = await _queue_last_chance_reminders(
            session,
            now_utc=now_utc,
            expires_before_utc=expires_before_utc(now_utc=now_utc),
            batch_size=batch_size,
        )
        expired_items = await _collect_expired_items(
            session,
            now_utc=now_utc,
            batch_size=batch_size,
        )
    return reminder_items, expired_items


async def _emit_deadline_notification_events(
    *,
    now_utc: datetime,
    reminder_events: list[dict[str, object]],
    expired_notice_events: list[dict[str, object]],
) -> None:
    if not reminder_events and not expired_notice_events:
        return
    async with SessionLocal.begin() as session:
        for payload in reminder_events:
            await emit_analytics_event(
                session,
                event_type="friend_challenge_last_chance_sent",
                source=EVENT_SOURCE_WORKER,
                happened_at=now_utc,
                user_id=None,
                payload=payload,
            )
        for payload in expired_notice_events:
            await emit_analytics_event(
                session,
                event_type="friend_challenge_expired_notice_sent",
                source=EVENT_SOURCE_WORKER,
                happened_at=now_utc,
                user_id=None,
                payload=payload,
            )


async def _send_deadline_notifications_with_events(
    *,
    now_utc: datetime,
    reminder_items: list[ReminderItem],
    expired_items: list[ExpiredItem],
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
    await _emit_deadline_notification_events(
        now_utc=now_utc,
        reminder_events=reminder_events,
        expired_notice_events=expired_notice_events,
    )
    return (
        reminders_sent,
        reminders_failed,
        expired_notices_sent,
        expired_notices_failed,
    )


async def run_friend_challenge_deadlines_async(
    *, batch_size: int = DEADLINE_BATCH_SIZE
) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    resolved_batch_size = resolved_deadline_batch_size(batch_size=batch_size)
    reminder_items, expired_items = await _collect_deadline_items(
        now_utc=now_utc,
        batch_size=resolved_batch_size,
    )
    (
        reminders_sent,
        reminders_failed,
        expired_notices_sent,
        expired_notices_failed,
    ) = await _send_deadline_notifications_with_events(
        now_utc=now_utc,
        reminder_items=reminder_items,
        expired_items=expired_items,
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
