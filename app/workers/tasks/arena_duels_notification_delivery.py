from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.analytics_events import BERLIN_TIMEZONE
from app.game.arena_duels.constants import ARENA_BEATEN_NOTIFICATION_EVENT
from app.game.arena_duels.types import ArenaBeatenNotification
from app.workers.tasks.arena_duels_notification_content import (
    build_arena_beaten_notification_keyboard,
    build_notification_text,
    format_user_label,
)
from app.workers.tasks.arena_duels_notification_payload import notification_payload


@dataclass(frozen=True, slots=True)
class ArenaBeatenNotificationDeps:
    session_local: Any
    analytics_repo: Any
    users_repo: Any


async def send_arena_beaten_notification_with_bot(
    *,
    bot,
    notification: ArenaBeatenNotification,
    happened_at: datetime,
    source: str,
    deps: ArenaBeatenNotificationDeps,
) -> dict[str, int]:
    payload = notification_payload(notification)
    local_date_berlin = happened_at.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()

    async with deps.session_local.begin() as session:
        if await _notification_already_sent(session, notification, payload, deps):
            return {"sent_total": 0, "failed_total": 0, "skipped_total": 1}

        previous_user, new_best_user = await _load_notification_users(session, notification, deps)
        if previous_user is None:
            return {"sent_total": 0, "failed_total": 1, "skipped_total": 0}
        if not await _send_notification_message(bot, notification, previous_user, new_best_user):
            return {"sent_total": 0, "failed_total": 1, "skipped_total": 0}

        await deps.analytics_repo.create_arena_beaten_notification_event_once(
            session,
            event_type=ARENA_BEATEN_NOTIFICATION_EVENT,
            source=source,
            user_id=notification.previous_best_user_id,
            local_date_berlin=local_date_berlin,
            payload=payload,
            happened_at=happened_at,
        )

    return {"sent_total": 1, "failed_total": 0, "skipped_total": 0}


async def _notification_already_sent(
    session,
    notification: ArenaBeatenNotification,
    payload: dict[str, object],
    deps: ArenaBeatenNotificationDeps,
) -> bool:
    await deps.analytics_repo.lock_arena_beaten_notification_event_key(
        session,
        event_type=ARENA_BEATEN_NOTIFICATION_EVENT,
        user_id=notification.previous_best_user_id,
        payload=payload,
    )
    return await deps.analytics_repo.has_arena_beaten_notification_event(
        session,
        event_type=ARENA_BEATEN_NOTIFICATION_EVENT,
        user_id=notification.previous_best_user_id,
        payload=payload,
    )


async def _load_notification_users(
    session,
    notification: ArenaBeatenNotification,
    deps: ArenaBeatenNotificationDeps,
):
    users = await deps.users_repo.list_by_ids(
        session,
        [notification.previous_best_user_id, notification.new_best_user_id],
    )
    users_by_id = {int(user.id): user for user in users}
    return (
        users_by_id.get(notification.previous_best_user_id),
        users_by_id.get(notification.new_best_user_id),
    )


async def _send_notification_message(
    bot,
    notification: ArenaBeatenNotification,
    previous_user,
    new_best_user,
) -> bool:
    challenger_label = format_user_label(
        username=getattr(new_best_user, "username", None),
        first_name=getattr(new_best_user, "first_name", None),
        fallback=f"Spieler #{notification.new_best_user_id}",
    )
    try:
        await bot.send_message(
            chat_id=int(previous_user.telegram_user_id),
            text=build_notification_text(
                notification=notification,
                challenger_label=challenger_label,
            ),
            reply_markup=build_arena_beaten_notification_keyboard(
                source_attempt_id=str(notification.new_best_attempt_id),
            ),
        )
    except Exception:
        return False
    return True
