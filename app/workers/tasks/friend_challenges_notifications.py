from __future__ import annotations

from datetime import datetime

from app.bot.application import build_bot
from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_finished_keyboard,
    build_friend_challenge_next_keyboard,
)
from app.workers.tasks.friend_challenges_utils import (
    format_remaining_hhmm,
    resolve_telegram_targets,
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
    user_ids: set[int] = set()
    for item in reminder_items:
        creator_user_id = item["creator_user_id"]
        assert isinstance(creator_user_id, int)
        user_ids.add(creator_user_id)
        opponent_user_id = item["opponent_user_id"]
        if isinstance(opponent_user_id, int):
            user_ids.add(opponent_user_id)
    for item in expired_items:
        creator_user_id = item["creator_user_id"]
        assert isinstance(creator_user_id, int)
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
            if not isinstance(expires_at, datetime):
                continue
            hours, minutes = format_remaining_hhmm(now_utc=now_utc, expires_at=expires_at)
            text = (
                f"⏳ Dein Duell läuft bald ab ({hours:02d}:{minutes:02d}h). " "Jetzt weiterspielen!"
            )
            challenge_id = str(item["challenge_id"])
            creator_user_id = item["creator_user_id"]
            assert isinstance(creator_user_id, int)
            target_user_ids = [creator_user_id]
            opponent_user_id = item["opponent_user_id"]
            if isinstance(opponent_user_id, int):
                target_user_ids.append(opponent_user_id)

            sent_to = 0
            failed_to = 0
            for target_user_id in target_user_ids:
                telegram_user_id = telegram_targets.get(target_user_id)
                if telegram_user_id is None:
                    failed_to += 1
                    continue
                try:
                    await bot.send_message(
                        chat_id=telegram_user_id,
                        text=text,
                        reply_markup=build_friend_challenge_next_keyboard(
                            challenge_id=challenge_id
                        ),
                    )
                    sent_to += 1
                except Exception:
                    failed_to += 1

            reminders_sent += sent_to
            reminders_failed += failed_to
            reminder_events.append(
                {
                    "challenge_id": challenge_id,
                    "sent_to": sent_to,
                    "failed_to": failed_to,
                    "expires_at": expires_at.isoformat(),
                }
            )

        for item in expired_items:
            challenge_id = str(item["challenge_id"])
            creator_user_id = item["creator_user_id"]
            assert isinstance(creator_user_id, int)
            opponent_user_id = item["opponent_user_id"]
            creator_score = item["creator_score"]
            opponent_score = item["opponent_score"]
            assert isinstance(creator_score, int)
            assert isinstance(opponent_score, int)

            sent_to = 0
            failed_to = 0

            creator_telegram = telegram_targets.get(creator_user_id)
            if creator_telegram is None:
                failed_to += 1
            else:
                try:
                    await bot.send_message(
                        chat_id=creator_telegram,
                        text=(
                            "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
                            f"Finaler Score: Du {creator_score} | Gegner {opponent_score}."
                        ),
                        reply_markup=build_friend_challenge_finished_keyboard(
                            challenge_id=challenge_id
                        ),
                    )
                    sent_to += 1
                except Exception:
                    failed_to += 1

            if isinstance(opponent_user_id, int):
                opponent_telegram = telegram_targets.get(opponent_user_id)
                if opponent_telegram is None:
                    failed_to += 1
                else:
                    try:
                        await bot.send_message(
                            chat_id=opponent_telegram,
                            text=(
                                "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
                                f"Finaler Score: Du {opponent_score} | Gegner {creator_score}."
                            ),
                            reply_markup=build_friend_challenge_finished_keyboard(
                                challenge_id=challenge_id
                            ),
                        )
                        sent_to += 1
                    except Exception:
                        failed_to += 1

            expired_notices_sent += sent_to
            expired_notices_failed += failed_to
            expired_notice_events.append(
                {
                    "challenge_id": challenge_id,
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
