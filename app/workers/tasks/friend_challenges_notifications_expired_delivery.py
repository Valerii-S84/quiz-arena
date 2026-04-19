from __future__ import annotations

from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_finished_keyboard,
    build_friend_pending_expired_keyboard,
)
from app.workers.tasks.friend_challenges_notifications_delivery import send_message_safely


async def _send_pending_expired_notice(
    *,
    bot,
    challenge_id: str,
    creator_chat: int | None,
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


async def deliver_expired_notice(
    *,
    bot,
    challenge_id: str,
    creator_chat: int | None,
    opponent_chat: int | None,
    creator_score: int,
    opponent_score: int,
    status: str,
    previous_status: str,
    has_opponent: bool,
) -> tuple[int, int]:
    if status == "EXPIRED" and previous_status == "PENDING":
        return await _send_pending_expired_notice(
            bot=bot,
            challenge_id=challenge_id,
            creator_chat=creator_chat,
        )
    creator_text, opponent_text = (
        (
            "⌛ Walkover. Duell beendet.\n"
            f"Finaler Score: Du {creator_score} | Gegner {opponent_score}.",
            "⌛ Walkover. Duell beendet.\n"
            f"Finaler Score: Du {opponent_score} | Gegner {creator_score}.",
        )
        if status == "WALKOVER"
        else (
            "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
            f"Finaler Score: Du {creator_score} | Gegner {opponent_score}.",
            "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
            f"Finaler Score: Du {opponent_score} | Gegner {creator_score}.",
        )
    )
    return await _send_finished_notice(
        bot=bot,
        challenge_id=challenge_id,
        creator_chat=creator_chat,
        opponent_chat=opponent_chat,
        creator_text=creator_text,
        opponent_text=opponent_text,
        has_opponent=has_opponent,
    )
