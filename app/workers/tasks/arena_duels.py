from __future__ import annotations

from datetime import datetime, timezone

from app.bot.application import build_bot
from app.core.analytics_events import EVENT_SOURCE_WORKER
from app.db.repo.analytics_repo import AnalyticsRepo
from app.db.repo.arena_duels_repo import ArenaDuelsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.arena_duels.types import ArenaBeatenNotification
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.task_heartbeat import run_tracked_async_job
from app.workers.tasks.arena_duels_notification_content import (
    build_arena_beaten_notification_keyboard,
)
from app.workers.tasks.arena_duels_notification_delivery import (
    ArenaBeatenNotificationDeps,
    send_arena_beaten_notification_with_bot,
)
from app.workers.tasks.arena_duels_notification_payload import notification_from_payload
from app.workers.tasks.arena_duels_schedule import configure_arena_duels_schedule


async def expire_arena_duels(*, now_utc: datetime | None = None) -> dict[str, int]:
    resolved_now_utc = now_utc or datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        expired_active_total = await ArenaDuelsRepo.expire_active_duels(
            session,
            now_utc=resolved_now_utc,
        )
        expired_draft_total = await ArenaDuelsRepo.expire_draft_duels(
            session,
            now_utc=resolved_now_utc,
        )
    return {
        "expired_active_total": expired_active_total,
        "expired_draft_total": expired_draft_total,
    }


async def send_arena_beaten_notification(
    *,
    notification: ArenaBeatenNotification,
    happened_at: datetime,
    bot=None,
    source: str = EVENT_SOURCE_WORKER,
) -> dict[str, int]:
    active_bot = bot or build_bot()
    owns_bot = bot is None
    try:
        return await send_arena_beaten_notification_with_bot(
            bot=active_bot,
            notification=notification,
            happened_at=happened_at,
            source=source,
            deps=ArenaBeatenNotificationDeps(
                session_local=SessionLocal,
                analytics_repo=AnalyticsRepo,
                users_repo=UsersRepo,
            ),
        )
    finally:
        if owns_bot:
            await active_bot.session.close()


@celery_app.task(name="app.workers.tasks.arena_duels.send_arena_beaten_notification_task")
def send_arena_beaten_notification_task(
    notification_payload: dict[str, object],
    happened_at_iso: str,
) -> dict[str, int]:
    return run_async_job(
        send_arena_beaten_notification(
            notification=notification_from_payload(notification_payload),
            happened_at=datetime.fromisoformat(happened_at_iso),
        )
    )


@celery_app.task(name="app.workers.tasks.arena_duels.expire_arena_duels")
def expire_arena_duels_task() -> dict[str, int]:
    task_name = "app.workers.tasks.arena_duels.expire_arena_duels"
    return run_tracked_async_job(
        task_name=task_name,
        schedule_key="arena-duel-expiry-every-5-minutes",
        awaitable=expire_arena_duels(),
    )


configure_arena_duels_schedule(celery_app)


__all__ = [
    "build_arena_beaten_notification_keyboard",
    "expire_arena_duels",
    "expire_arena_duels_task",
    "send_arena_beaten_notification",
    "send_arena_beaten_notification_task",
]
