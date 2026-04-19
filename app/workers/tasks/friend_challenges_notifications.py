from __future__ import annotations

from datetime import datetime

from app.bot.application import build_bot
from app.workers.tasks.friend_challenges_notifications_expired import send_expired_notices
from app.workers.tasks.friend_challenges_notifications_reminders import send_deadline_reminders
from app.workers.tasks.friend_challenges_utils import resolve_telegram_targets


def _deadline_notification_user_ids(
    *,
    reminder_items: list[dict[str, object]],
    expired_items: list[dict[str, object]],
) -> set[int]:
    user_ids: set[int] = set()
    for item in reminder_items:
        target_user_id = item["target_user_id"]
        if isinstance(target_user_id, int):
            user_ids.add(target_user_id)
    for item in expired_items:
        creator_user_id = item["creator_user_id"]
        if isinstance(creator_user_id, int):
            user_ids.add(creator_user_id)
        opponent_user_id = item["opponent_user_id"]
        if isinstance(opponent_user_id, int):
            user_ids.add(opponent_user_id)
    return user_ids


async def _send_deadline_notifications_with_bot(
    *,
    bot,
    now_utc: datetime,
    reminder_items: list[dict[str, object]],
    expired_items: list[dict[str, object]],
    telegram_targets: dict[int, int],
) -> tuple[int, int, int, int, list[dict[str, object]], list[dict[str, object]]]:
    reminders_sent, reminders_failed, reminder_events = await send_deadline_reminders(
        bot=bot,
        now_utc=now_utc,
        reminder_items=reminder_items,
        telegram_targets=telegram_targets,
    )
    (
        expired_notices_sent,
        expired_notices_failed,
        expired_notice_events,
    ) = await send_expired_notices(
        bot=bot,
        expired_items=expired_items,
        telegram_targets=telegram_targets,
    )
    return (
        reminders_sent,
        reminders_failed,
        expired_notices_sent,
        expired_notices_failed,
        reminder_events,
        expired_notice_events,
    )


async def send_deadline_notifications(
    *,
    now_utc: datetime,
    reminder_items: list[dict[str, object]],
    expired_items: list[dict[str, object]],
) -> tuple[
    int,
    int,
    int,
    int,
    list[dict[str, object]],
    list[dict[str, object]],
]:
    telegram_targets = await resolve_telegram_targets(
        _deadline_notification_user_ids(
            reminder_items=reminder_items,
            expired_items=expired_items,
        )
    )

    bot = build_bot()
    try:
        return await _send_deadline_notifications_with_bot(
            bot=bot,
            now_utc=now_utc,
            reminder_items=reminder_items,
            expired_items=expired_items,
            telegram_targets=telegram_targets,
        )
    finally:
        await bot.session.close()
