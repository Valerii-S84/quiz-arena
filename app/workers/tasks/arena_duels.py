from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.application import build_bot
from app.core.analytics_events import BERLIN_TIMEZONE, EVENT_SOURCE_WORKER
from app.db.repo.analytics_repo import AnalyticsRepo
from app.db.repo.arena_duels_repo import ArenaDuelsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.arena_duels.constants import ARENA_BEATEN_NOTIFICATION_EVENT
from app.game.arena_duels.types import ArenaBeatenNotification
from app.game.duels.constants import ARENA_LIST_CALLBACK
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.arena_duels_schedule import configure_arena_duels_schedule


def build_arena_beaten_notification_keyboard(
    *,
    source_attempt_id: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔁 Revanche",
                    callback_data=f"arena:revanche:{source_attempt_id}",
                )
            ],
            [InlineKeyboardButton(text="🏟 Zur Arena", callback_data=ARENA_LIST_CALLBACK)],
        ]
    )


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
        return await _send_arena_beaten_notification_with_bot(
            bot=active_bot,
            notification=notification,
            happened_at=happened_at,
            source=source,
        )
    finally:
        if owns_bot:
            await active_bot.session.close()


async def _send_arena_beaten_notification_with_bot(
    *,
    bot,
    notification: ArenaBeatenNotification,
    happened_at: datetime,
    source: str,
) -> dict[str, int]:
    payload = _notification_payload(notification)
    local_date_berlin = happened_at.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()
    async with SessionLocal.begin() as session:
        await AnalyticsRepo.lock_arena_beaten_notification_event_key(
            session,
            event_type=ARENA_BEATEN_NOTIFICATION_EVENT,
            user_id=notification.previous_best_user_id,
            payload=payload,
        )
        already_sent = await AnalyticsRepo.has_arena_beaten_notification_event(
            session,
            event_type=ARENA_BEATEN_NOTIFICATION_EVENT,
            user_id=notification.previous_best_user_id,
            payload=payload,
        )
        if already_sent:
            return {"sent_total": 0, "failed_total": 0, "skipped_total": 1}

        users = await UsersRepo.list_by_ids(
            session,
            [notification.previous_best_user_id, notification.new_best_user_id],
        )
        users_by_id = {int(user.id): user for user in users}
        previous_user = users_by_id.get(notification.previous_best_user_id)
        new_best_user = users_by_id.get(notification.new_best_user_id)
        if previous_user is None:
            return {"sent_total": 0, "failed_total": 1, "skipped_total": 0}

        challenger_label = _format_user_label(
            username=getattr(new_best_user, "username", None),
            first_name=getattr(new_best_user, "first_name", None),
            fallback=f"Spieler #{notification.new_best_user_id}",
        )
        try:
            await bot.send_message(
                chat_id=int(previous_user.telegram_user_id),
                text=_build_notification_text(
                    notification=notification,
                    challenger_label=challenger_label,
                ),
                reply_markup=build_arena_beaten_notification_keyboard(
                    source_attempt_id=str(notification.new_best_attempt_id),
                ),
            )
        except Exception:
            return {"sent_total": 0, "failed_total": 1, "skipped_total": 0}
        await AnalyticsRepo.create_arena_beaten_notification_event_once(
            session,
            event_type=ARENA_BEATEN_NOTIFICATION_EVENT,
            source=source,
            user_id=notification.previous_best_user_id,
            local_date_berlin=local_date_berlin,
            payload=payload,
            happened_at=happened_at,
        )
    return {"sent_total": 1, "failed_total": 0, "skipped_total": 0}


def _notification_payload(notification: ArenaBeatenNotification) -> dict[str, object]:
    return {
        "arena_duel_id": str(notification.arena_duel_id),
        "previous_best_attempt_id": str(notification.previous_best_attempt_id),
        "previous_best_user_id": notification.previous_best_user_id,
        "previous_best_score": notification.previous_best_score,
        "previous_best_time_ms": notification.previous_best_time_ms,
        "new_best_attempt_id": str(notification.new_best_attempt_id),
        "new_best_user_id": notification.new_best_user_id,
        "new_best_score": notification.new_best_score,
        "new_best_time_ms": notification.new_best_time_ms,
        "notification_type": notification.notification_type,
    }


def _build_notification_text(
    *,
    notification: ArenaBeatenNotification,
    challenger_label: str,
) -> str:
    previous_score = _format_score_time(
        notification.previous_best_score,
        notification.previous_best_time_ms,
    )
    new_score = _format_score_time(
        notification.new_best_score,
        notification.new_best_time_ms,
    )
    return (
        "⚔️ Dein Arena-Duell wurde geschlagen.\n\n"
        f"{challenger_label} hat dein Ergebnis übertroffen.\n\n"
        f"Du:\n{previous_score}\n\n"
        f"{challenger_label}:\n{new_score}"
    )


def _format_score_time(score: int, time_ms: int) -> str:
    seconds = max(0, int(round(time_ms / 1000)))
    return f"{score}/7 · {seconds // 60:02d}:{seconds % 60:02d}"


def _format_user_label(
    *,
    username: str | None,
    first_name: str | None,
    fallback: str,
) -> str:
    if username is not None and username.strip():
        return f"@{username.strip().lstrip('@')}"
    if first_name is not None and first_name.strip():
        return first_name.strip()
    return fallback


@celery_app.task(name="app.workers.tasks.arena_duels.send_arena_beaten_notification_task")
def send_arena_beaten_notification_task(
    notification_payload: dict[str, object],
    happened_at_iso: str,
) -> dict[str, int]:
    return run_async_job(
        send_arena_beaten_notification(
            notification=_notification_from_payload(notification_payload),
            happened_at=datetime.fromisoformat(happened_at_iso),
        )
    )


@celery_app.task(name="app.workers.tasks.arena_duels.expire_arena_duels")
def expire_arena_duels_task() -> dict[str, int]:
    return run_async_job(expire_arena_duels())


configure_arena_duels_schedule(celery_app)


def _notification_from_payload(payload: dict[str, object]) -> ArenaBeatenNotification:
    from uuid import UUID

    return ArenaBeatenNotification(
        arena_duel_id=UUID(str(payload["arena_duel_id"])),
        previous_best_attempt_id=UUID(str(payload["previous_best_attempt_id"])),
        previous_best_user_id=_payload_int(payload, "previous_best_user_id"),
        previous_best_score=_payload_int(payload, "previous_best_score"),
        previous_best_time_ms=_payload_int(payload, "previous_best_time_ms"),
        new_best_attempt_id=UUID(str(payload["new_best_attempt_id"])),
        new_best_user_id=_payload_int(payload, "new_best_user_id"),
        new_best_score=_payload_int(payload, "new_best_score"),
        new_best_time_ms=_payload_int(payload, "new_best_time_ms"),
        notification_type=str(payload["notification_type"]),
    )


def _payload_int(payload: dict[str, object], key: str) -> int:
    value = payload[key]
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise ValueError(f"Invalid arena notification payload field: {key}")


__all__ = [
    "build_arena_beaten_notification_keyboard",
    "expire_arena_duels",
    "expire_arena_duels_task",
    "send_arena_beaten_notification",
    "send_arena_beaten_notification_task",
]
