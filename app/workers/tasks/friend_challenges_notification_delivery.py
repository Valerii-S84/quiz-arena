from __future__ import annotations

from datetime import datetime

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_finished_keyboard,
    build_friend_challenge_next_keyboard,
    build_friend_pending_expired_keyboard,
)
from app.workers.tasks.friend_challenges_notification_content import (
    build_expired_duel_texts,
    build_unplayed_friend_challenge_text,
)
from app.workers.tasks.friend_challenges_utils import format_remaining_hhmm


async def _send_message(
    *,
    bot: Bot,
    chat_id: int | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
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
        # Deadline notifications are best-effort; one blocked chat must not abort the batch.
        return False


async def send_last_chance_reminders(
    *,
    bot: Bot,
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
        is_unplayed = item.get("reminder_kind") == "unplayed"
        text = (
            build_unplayed_friend_challenge_text(can_publish_to_arena=True)
            if is_unplayed
            else f"⏳ Dein Freund hat gespielt. Jetzt bist du dran! ({hours:02d}:{minutes:02d}h)"
        )
        reply_markup = (
            build_friend_pending_expired_keyboard(
                challenge_id=str(item["challenge_id"]),
                can_publish_to_arena=True,
            )
            if is_unplayed
            else build_friend_challenge_next_keyboard(challenge_id=str(item["challenge_id"]))
        )
        sent = await _send_message(
            bot=bot,
            chat_id=telegram_targets.get(target_user_id),
            text=text,
            reply_markup=reply_markup,
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
                "reminder_kind": str(item.get("reminder_kind") or "turn"),
            }
        )
    return reminders_sent, reminders_failed, reminder_events


async def _send_expired_notice(
    *,
    bot: Bot,
    item: dict[str, object],
    telegram_targets: dict[int, int],
) -> tuple[int, int]:
    challenge_id = str(item["challenge_id"])
    creator_user_id = item["creator_user_id"]
    opponent_user_id = item["opponent_user_id"]
    creator_score_raw = item["creator_score"]
    opponent_score_raw = item["opponent_score"]
    if not isinstance(creator_score_raw, int) or not isinstance(opponent_score_raw, int):
        return 0, 0
    creator_score = creator_score_raw
    opponent_score = opponent_score_raw
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
            text=build_unplayed_friend_challenge_text(can_publish_to_arena=False),
            reply_markup=build_friend_pending_expired_keyboard(
                challenge_id=challenge_id,
                can_publish_to_arena=False,
            ),
        )
        sent_to += int(sent)
        failed_to += int(not sent)
        return sent_to, failed_to

    creator_text, opponent_text = build_expired_duel_texts(
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


async def send_expired_notices(
    *,
    bot: Bot,
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
