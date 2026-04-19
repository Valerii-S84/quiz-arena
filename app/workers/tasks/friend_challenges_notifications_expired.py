from __future__ import annotations

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_finished_keyboard,
    build_friend_pending_expired_keyboard,
)
from app.workers.tasks.friend_challenges_notifications_delivery import send_message_safely
from app.workers.tasks.friend_challenges_notifications_expired_payloads import (
    expired_notice_context,
    expired_notice_result,
    expired_scores,
)


async def _send_pending_expired_notice(
    *, bot, challenge_id: str, creator_chat: int | None
) -> tuple[int, int]:
    sent = await send_message_safely(
        bot=bot,
        chat_id=creator_chat,
        text="⏳ Niemand hat angenommen.",
        reply_markup=build_friend_pending_expired_keyboard(challenge_id=challenge_id),
    )
    return int(sent), int(not sent)


async def _send_finished_notice(
    *,
    bot,
    challenge_id: str,
    creator_chat: int | None,
    opponent_chat: int | None,
    creator_score: int,
    opponent_score: int,
    creator_text: str,
    opponent_text: str,
    has_opponent: bool,
) -> tuple[int, int]:
    sent_to = 0
    failed_to = 0
    reply_markup = build_friend_challenge_finished_keyboard(challenge_id=challenge_id)
    creator_sent = await send_message_safely(
        bot=bot,
        chat_id=creator_chat,
        text=creator_text,
        reply_markup=reply_markup,
    )
    sent_to += int(creator_sent)
    failed_to += int(not creator_sent)
    if not has_opponent:
        return sent_to, failed_to
    opponent_sent = await send_message_safely(
        bot=bot,
        chat_id=opponent_chat,
        text=opponent_text,
        reply_markup=reply_markup,
    )
    sent_to += int(opponent_sent)
    failed_to += int(not opponent_sent)
    return sent_to, failed_to


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
    return await _send_finished_notice(
        bot=bot,
        challenge_id=challenge_id,
        creator_chat=creator_chat,
        opponent_chat=opponent_chat,
        creator_score=creator_score,
        opponent_score=opponent_score,
        creator_text=(
            "⌛ Walkover. Duell beendet.\n"
            f"Finaler Score: Du {creator_score} | Gegner {opponent_score}."
        ),
        opponent_text=(
            "⌛ Walkover. Duell beendet.\n"
            f"Finaler Score: Du {opponent_score} | Gegner {creator_score}."
        ),
        has_opponent=has_opponent,
    )


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
    return await _send_finished_notice(
        bot=bot,
        challenge_id=challenge_id,
        creator_chat=creator_chat,
        opponent_chat=opponent_chat,
        creator_score=creator_score,
        opponent_score=opponent_score,
        creator_text=(
            "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
            f"Finaler Score: Du {creator_score} | Gegner {opponent_score}."
        ),
        opponent_text=(
            "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
            f"Finaler Score: Du {opponent_score} | Gegner {creator_score}."
        ),
        has_opponent=has_opponent,
    )


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


async def _send_expired_notice_item(
    *,
    bot,
    item: dict[str, object],
    telegram_targets: dict[int, int],
) -> tuple[int, int, dict[str, object]] | None:
    scores = expired_scores(item)
    if scores is None:
        return None
    creator_score, opponent_score = scores
    challenge_id, status, previous_status, creator_chat, opponent_chat = expired_notice_context(
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
    return expired_notice_result(
        challenge_id=challenge_id,
        status=status,
        previous_status=previous_status,
        sent_to=sent_to,
        failed_to=failed_to,
        creator_score=creator_score,
        opponent_score=opponent_score,
    )


async def send_expired_notices(
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
