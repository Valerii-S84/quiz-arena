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


async def _send_deadline_reminders(
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


def _expired_notice_targets(
    *,
    item: dict[str, object],
    telegram_targets: dict[int, int],
) -> tuple[int | None, int | None]:
    creator_user_id = item["creator_user_id"]
    opponent_user_id = item["opponent_user_id"]
    creator_chat = (
        telegram_targets.get(creator_user_id) if isinstance(creator_user_id, int) else None
    )
    opponent_chat = (
        telegram_targets.get(opponent_user_id) if isinstance(opponent_user_id, int) else None
    )
    return creator_chat, opponent_chat


async def _send_pending_expired_notice(
    *, bot, challenge_id: str, creator_chat: int | None
) -> tuple[int, int]:
    sent = await _send_message(
        bot=bot,
        chat_id=creator_chat,
        text="⏳ Niemand hat angenommen.",
        reply_markup=build_friend_pending_expired_keyboard(challenge_id=challenge_id),
    )
    return int(sent), int(not sent)


async def _send_walkover_notice(
    *,
    bot,
    challenge_id: str,
    creator_chat: int | None,
    opponent_chat: int | None,
    creator_score: int,
    opponent_score: int,
    has_opponent: bool,
) -> tuple[int, int]:
    sent_to = 0
    failed_to = 0
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
    if not has_opponent:
        return sent_to, failed_to
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
    return sent_to, failed_to


async def _send_standard_expired_notice(
    *,
    bot,
    challenge_id: str,
    creator_chat: int | None,
    opponent_chat: int | None,
    creator_score: int,
    opponent_score: int,
    has_opponent: bool,
) -> tuple[int, int]:
    sent_to = 0
    failed_to = 0
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
    if not has_opponent:
        return sent_to, failed_to
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
    return sent_to, failed_to


async def _deliver_expired_notice(
    *,
    bot,
    item: dict[str, object],
    challenge_id: str,
    creator_chat: int | None,
    opponent_chat: int | None,
    creator_score: int,
    opponent_score: int,
    status: str,
    previous_status: str,
) -> tuple[int, int]:
    has_opponent = isinstance(item["opponent_user_id"], int)
    if status == "EXPIRED" and previous_status == "PENDING":
        return await _send_pending_expired_notice(
            bot=bot,
            challenge_id=challenge_id,
            creator_chat=creator_chat,
        )
    if status == "WALKOVER":
        return await _send_walkover_notice(
            bot=bot,
            challenge_id=challenge_id,
            creator_chat=creator_chat,
            opponent_chat=opponent_chat,
            creator_score=creator_score,
            opponent_score=opponent_score,
            has_opponent=has_opponent,
        )
    return await _send_standard_expired_notice(
        bot=bot,
        challenge_id=challenge_id,
        creator_chat=creator_chat,
        opponent_chat=opponent_chat,
        creator_score=creator_score,
        opponent_score=opponent_score,
        has_opponent=has_opponent,
    )


def _expired_notice_event_payload(
    *,
    item: dict[str, object],
    challenge_id: str,
    status: str,
    previous_status: str,
    sent_to: int,
    failed_to: int,
    creator_score: int,
    opponent_score: int,
) -> dict[str, object]:
    del item
    return {
        "challenge_id": challenge_id,
        "status": status,
        "previous_status": previous_status,
        "sent_to": sent_to,
        "failed_to": failed_to,
        "creator_score": creator_score,
        "opponent_score": opponent_score,
    }


def _expired_notice_result(
    *,
    item: dict[str, object],
    challenge_id: str,
    status: str,
    previous_status: str,
    sent_to: int,
    failed_to: int,
    creator_score: int,
    opponent_score: int,
) -> tuple[int, int, dict[str, object]]:
    return (
        sent_to,
        failed_to,
        _expired_notice_event_payload(
            item=item,
            challenge_id=challenge_id,
            status=status,
            previous_status=previous_status,
            sent_to=sent_to,
            failed_to=failed_to,
            creator_score=creator_score,
            opponent_score=opponent_score,
        ),
    )


def _expired_scores(item: dict[str, object]) -> tuple[int, int] | None:
    creator_score = item["creator_score"]
    opponent_score = item["opponent_score"]
    if not isinstance(creator_score, int) or not isinstance(opponent_score, int):
        return None
    return creator_score, opponent_score


def _expired_notice_context(
    *,
    item: dict[str, object],
    telegram_targets: dict[int, int],
) -> tuple[str, str, str, int | None, int | None]:
    challenge_id = str(item["challenge_id"])
    status = str(item.get("status") or "")
    previous_status = str(item.get("previous_status") or "")
    creator_chat, opponent_chat = _expired_notice_targets(
        item=item,
        telegram_targets=telegram_targets,
    )
    return challenge_id, status, previous_status, creator_chat, opponent_chat


async def _send_expired_notice_item(
    *,
    bot,
    item: dict[str, object],
    telegram_targets: dict[int, int],
) -> tuple[int, int, dict[str, object]] | None:
    scores = _expired_scores(item)
    if scores is None:
        return None
    creator_score, opponent_score = scores
    challenge_id, status, previous_status, creator_chat, opponent_chat = _expired_notice_context(
        item=item,
        telegram_targets=telegram_targets,
    )
    sent_to, failed_to = await _deliver_expired_notice(
        bot=bot,
        item=item,
        challenge_id=challenge_id,
        creator_chat=creator_chat,
        opponent_chat=opponent_chat,
        creator_score=creator_score,
        opponent_score=opponent_score,
        status=status,
        previous_status=previous_status,
    )
    return _expired_notice_result(
        item=item,
        challenge_id=challenge_id,
        status=status,
        previous_status=previous_status,
        sent_to=sent_to,
        failed_to=failed_to,
        creator_score=creator_score,
        opponent_score=opponent_score,
    )


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
        notice_result = await _send_expired_notice_item(
            bot=bot,
            item=item,
            telegram_targets=telegram_targets,
        )
        if notice_result is None:
            continue
        sent_to, failed_to, event = notice_result
        expired_notices_sent += sent_to
        expired_notices_failed += failed_to
        expired_notice_events.append(event)
    return expired_notices_sent, expired_notices_failed, expired_notice_events


async def _send_deadline_notifications_with_bot(
    *,
    bot,
    now_utc: datetime,
    reminder_items: list[dict[str, object]],
    expired_items: list[dict[str, object]],
    telegram_targets: dict[int, int],
) -> tuple[int, int, int, int, list[dict[str, object]], list[dict[str, object]]]:
    reminders_sent, reminders_failed, reminder_events = await _send_deadline_reminders(
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
