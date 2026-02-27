from __future__ import annotations

from datetime import datetime

from app.bot.application import build_bot
from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_finished_keyboard,
    build_friend_challenge_next_keyboard,
    build_friend_pending_expired_keyboard,
)
from app.workers.tasks.friend_challenges_utils import (
    format_remaining_hhmm,
    resolve_telegram_targets,
)


async def _send_message(*, bot, chat_id: int | None, text: str, reply_markup=None) -> bool:
    if chat_id is None:
        return False
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )
        return True
    except Exception:
        return False


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
    telegram_targets = await resolve_telegram_targets(user_ids)

    reminders_sent = 0
    reminders_failed = 0
    expired_notices_sent = 0
    expired_notices_failed = 0
    reminder_events: list[dict[str, object]] = []
    expired_notice_events: list[dict[str, object]] = []

    bot = build_bot()
    try:
        for item in reminder_items:
            expires_at = item["expires_at"]
            target_user_id = item["target_user_id"]
            if not isinstance(expires_at, datetime) or not isinstance(target_user_id, int):
                continue
            hours, minutes = format_remaining_hhmm(now_utc=now_utc, expires_at=expires_at)
            sent = await _send_message(
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

        for item in expired_items:
            challenge_id = str(item["challenge_id"])
            creator_user_id = item["creator_user_id"]
            opponent_user_id = item["opponent_user_id"]
            creator_score_raw = item["creator_score"]
            opponent_score_raw = item["opponent_score"]
            if not isinstance(creator_score_raw, int) or not isinstance(opponent_score_raw, int):
                continue
            creator_score = creator_score_raw
            opponent_score = opponent_score_raw
            status = str(item.get("status") or "")
            previous_status = str(item.get("previous_status") or "")

            sent_to = 0
            failed_to = 0
            creator_chat = telegram_targets.get(creator_user_id) if isinstance(creator_user_id, int) else None
            opponent_chat = telegram_targets.get(opponent_user_id) if isinstance(opponent_user_id, int) else None

            if status == "EXPIRED" and previous_status == "PENDING":
                sent = await _send_message(
                    bot=bot,
                    chat_id=creator_chat,
                    text="⏳ Niemand hat angenommen.",
                    reply_markup=build_friend_pending_expired_keyboard(challenge_id=challenge_id),
                )
                sent_to += int(sent)
                failed_to += int(not sent)
            elif status == "WALKOVER":
                creator_sent = await _send_message(
                    bot=bot,
                    chat_id=creator_chat,
                    text=(
                        "⌛ Walkover. Duell beendet.\n"
                        f"Finaler Score: Du {creator_score} | Gegner {opponent_score}."
                    ),
                    reply_markup=build_friend_challenge_finished_keyboard(challenge_id=challenge_id),
                )
                sent_to += int(creator_sent)
                failed_to += int(not creator_sent)
                if isinstance(opponent_user_id, int):
                    opponent_sent = await _send_message(
                        bot=bot,
                        chat_id=opponent_chat,
                        text=(
                            "⌛ Walkover. Duell beendet.\n"
                            f"Finaler Score: Du {opponent_score} | Gegner {creator_score}."
                        ),
                        reply_markup=build_friend_challenge_finished_keyboard(challenge_id=challenge_id),
                    )
                    sent_to += int(opponent_sent)
                    failed_to += int(not opponent_sent)
            else:
                creator_sent = await _send_message(
                    bot=bot,
                    chat_id=creator_chat,
                    text=(
                        "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
                        f"Finaler Score: Du {creator_score} | Gegner {opponent_score}."
                    ),
                    reply_markup=build_friend_challenge_finished_keyboard(challenge_id=challenge_id),
                )
                sent_to += int(creator_sent)
                failed_to += int(not creator_sent)
                if isinstance(opponent_user_id, int):
                    opponent_sent = await _send_message(
                        bot=bot,
                        chat_id=opponent_chat,
                        text=(
                            "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
                            f"Finaler Score: Du {opponent_score} | Gegner {creator_score}."
                        ),
                        reply_markup=build_friend_challenge_finished_keyboard(challenge_id=challenge_id),
                    )
                    sent_to += int(opponent_sent)
                    failed_to += int(not opponent_sent)

            expired_notices_sent += sent_to
            expired_notices_failed += failed_to
            expired_notice_events.append(
                {
                    "challenge_id": challenge_id,
                    "status": status,
                    "previous_status": previous_status,
                    "sent_to": sent_to,
                    "failed_to": failed_to,
                    "creator_score": creator_score,
                    "opponent_score": opponent_score,
                }
            )
    finally:
        await bot.session.close()

    return (
        reminders_sent,
        reminders_failed,
        expired_notices_sent,
        expired_notices_failed,
        reminder_events,
        expired_notice_events,
    )
