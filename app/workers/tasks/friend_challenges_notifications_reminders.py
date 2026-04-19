from __future__ import annotations

from datetime import datetime

from app.bot.keyboards.friend_challenge import build_friend_challenge_next_keyboard
from app.workers.tasks.friend_challenges_notifications_delivery import send_message_safely
from app.workers.tasks.friend_challenges_utils import format_remaining_hhmm


async def send_deadline_reminders(
    *,
    bot,
    now_utc: datetime,
    reminder_items: list[dict[str, object]],
    telegram_targets: dict[int, int],
) -> tuple[int, int, list[dict[str, object]]]:
    reminders_sent = 0
    reminders_failed = 0
    reminder_events: list[dict[str, object]] = []
    for item in reminder_items:
        expires_at = item["expires_at"]
        target_user_id = item["target_user_id"]
        if not isinstance(expires_at, datetime) or not isinstance(target_user_id, int):
            continue
        hours, minutes = format_remaining_hhmm(now_utc=now_utc, expires_at=expires_at)
        sent = await send_message_safely(
            bot=bot,
            chat_id=telegram_targets.get(target_user_id),
            text=f"⏳ Gegner hat gespielt. Jetzt bist du dran! ({hours:02d}:{minutes:02d}h)",
            reply_markup=build_friend_challenge_next_keyboard(
                challenge_id=str(item["challenge_id"])
            ),
        )
        reminders_sent += int(sent)
        reminders_failed += int(not sent)
        reminder_events.append(
            {
                "challenge_id": str(item["challenge_id"]),
                "target_user_id": target_user_id,
                "sent_to": int(sent),
                "failed_to": int(not sent),
                "expires_at": expires_at.isoformat(),
            }
        )
    return reminders_sent, reminders_failed, reminder_events
