from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.game.arena_duels.constants import ARENA_BEATEN_NOTIFICATION_EVENT
from app.game.arena_duels.types import ArenaBeatenNotification


@dataclass(frozen=True, slots=True)
class ArenaBeatenNotificationDeps:
    session_local: Any
    analytics_repo: Any
    users_repo: Any


async def notification_already_sent(
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


async def load_notification_users(
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


__all__ = [
    "ArenaBeatenNotificationDeps",
    "load_notification_users",
    "notification_already_sent",
]
