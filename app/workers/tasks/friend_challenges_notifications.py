from __future__ import annotations

from datetime import datetime

from app.bot.application import build_bot
from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_finished_keyboard,
    build_friend_challenge_next_keyboard,
    build_friend_pending_expired_keyboard,
)
from app.bot.texts.de import TEXTS_DE
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


def _build_unplayed_friend_challenge_text(*, can_publish_to_arena: bool) -> str:
    hint_key = (
        "msg.friend.challenge.reminder.publish_hint"
        if can_publish_to_arena
        else "msg.friend.challenge.reminder.wait_or_close_hint"
    )
    return "\n\n".join(
        [
            TEXTS_DE["msg.friend.challenge.reminder.unplayed"],
            TEXTS_DE[hint_key],
        ]
    )


def _collect_deadline_user_ids(
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


async def _send_last_chance_reminders(
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
        sent = await _send_message(
            bot=bot,
            chat_id=telegram_targets.get(target_user_id),
            text=f"⏳ Dein Freund hat gespielt. Jetzt bist du dran! ({hours:02d}:{minutes:02d}h)",
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


def _build_expired_duel_texts(
    *,
    status: str,
    creator_score: int,
    opponent_score: int,
) -> tuple[str, str]:
    if status == "WALKOVER":
        return (
            "⌛ Duell kampflos beendet.\n"
            f"Endstand: Du {creator_score} | Freund {opponent_score}.",
            "⌛ Duell kampflos beendet.\n"
            f"Endstand: Du {opponent_score} | Freund {creator_score}.",
        )
    return (
        "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
        f"Endstand: Du {creator_score} | Freund {opponent_score}.",
        "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
        f"Endstand: Du {opponent_score} | Freund {creator_score}.",
    )


async def _send_expired_notice(
    *,
    bot,
    item: dict[str, object],
    telegram_targets: dict[int, int],
) -> tuple[int, int]:
    challenge_id = str(item["challenge_id"])
    creator_user_id = item["creator_user_id"]
    opponent_user_id = item["opponent_user_id"]
    creator_score = int(item["creator_score"])
    opponent_score = int(item["opponent_score"])
    status = str(item.get("status") or "")
    previous_status = str(item.get("previous_status") or "")

    sent_to = 0
    failed_to = 0
    creator_chat = (
        telegram_targets.get(creator_user_id) if isinstance(creator_user_id, int) else None
    )
    opponent_chat = (
        telegram_targets.get(opponent_user_id) if isinstance(opponent_user_id, int) else None
    )

    if status == "EXPIRED" and previous_status == "PENDING":
        sent = await _send_message(
            bot=bot,
            chat_id=creator_chat,
            text=_build_unplayed_friend_challenge_text(can_publish_to_arena=False),
            reply_markup=build_friend_pending_expired_keyboard(
                challenge_id=challenge_id,
                can_publish_to_arena=False,
            ),
        )
        sent_to += int(sent)
        failed_to += int(not sent)
        return sent_to, failed_to

    creator_text, opponent_text = _build_expired_duel_texts(
        status=status,
        creator_score=creator_score,
        opponent_score=opponent_score,
    )
    creator_sent = await _send_message(
        bot=bot,
        chat_id=creator_chat,
        text=creator_text,
        reply_markup=build_friend_challenge_finished_keyboard(challenge_id=challenge_id),
    )
    sent_to += int(creator_sent)
    failed_to += int(not creator_sent)
    if isinstance(opponent_user_id, int):
        opponent_sent = await _send_message(
            bot=bot,
            chat_id=opponent_chat,
            text=opponent_text,
            reply_markup=build_friend_challenge_finished_keyboard(challenge_id=challenge_id),
        )
        sent_to += int(opponent_sent)
        failed_to += int(not opponent_sent)
    return sent_to, failed_to


async def _send_expired_notices(
    *,
    bot,
    expired_items: list[dict[str, object]],
    telegram_targets: dict[int, int],
) -> tuple[int, int, list[dict[str, object]]]:
    expired_notices_sent = 0
    expired_notices_failed = 0
    expired_notice_events: list[dict[str, object]] = []
    for item in expired_items:
        creator_score_raw = item["creator_score"]
        opponent_score_raw = item["opponent_score"]
        if not isinstance(creator_score_raw, int) or not isinstance(opponent_score_raw, int):
            continue

        sent_to, failed_to = await _send_expired_notice(
            bot=bot,
            item=item,
            telegram_targets=telegram_targets,
        )
        expired_notices_sent += sent_to
        expired_notices_failed += failed_to
        expired_notice_events.append(
            {
                "challenge_id": str(item["challenge_id"]),
                "status": str(item.get("status") or ""),
                "previous_status": str(item.get("previous_status") or ""),
                "sent_to": sent_to,
                "failed_to": failed_to,
                "creator_score": creator_score_raw,
                "opponent_score": opponent_score_raw,
            }
        )
    return expired_notices_sent, expired_notices_failed, expired_notice_events


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
        _collect_deadline_user_ids(
            reminder_items=reminder_items,
            expired_items=expired_items,
        )
    )

    bot = build_bot()
    try:
        reminders_sent, reminders_failed, reminder_events = await _send_last_chance_reminders(
            bot=bot,
            now_utc=now_utc,
            reminder_items=reminder_items,
            telegram_targets=telegram_targets,
        )
        (
            expired_notices_sent,
            expired_notices_failed,
            expired_notice_events,
        ) = await _send_expired_notices(
            bot=bot,
            expired_items=expired_items,
            telegram_targets=telegram_targets,
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
