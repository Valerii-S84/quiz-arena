from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram.types import BufferedInputFile


@dataclass(frozen=True, slots=True)
class FriendChallengeProofCardsDeliveryResult:
    sent: int
    cached_reused: int
    new_creator_file_id: str | None
    new_opponent_file_id: str | None


async def deliver_friend_challenge_proof_cards(
    *,
    context: Any,
    build_bot_fn: Any,
    build_keyboard_fn: Any,
    build_caption_fn: Any,
    render_card_fn: Any,
    logger: Any,
) -> FriendChallengeProofCardsDeliveryResult:
    sent = 0
    cached_reused = 0
    new_creator_file_id: str | None = None
    new_opponent_file_id: str | None = None
    card_png = (
        render_card_fn(
            creator_name=context.creator_name,
            opponent_name=context.opponent_name,
            creator_score=context.creator_score,
            opponent_score=context.opponent_score,
            total_rounds=context.total_rounds,
            completed_at=context.completed_at,
        )
        if any(recipient.cached_file_id is None for recipient in context.recipients)
        else None
    )

    bot = build_bot_fn()
    keyboard = build_keyboard_fn(share_url="", challenge_id=context.challenge_id)
    try:
        for recipient in context.recipients:
            caption = build_caption_fn(
                challenge_id=context.challenge_id,
                status=context.status,
                role=recipient.role,
                creator_score=context.creator_score,
                opponent_score=context.opponent_score,
            )
            if recipient.cached_file_id:
                await bot.send_photo(
                    chat_id=recipient.chat_id,
                    photo=recipient.cached_file_id,
                    caption=caption,
                    reply_markup=keyboard,
                )
                sent += 1
                cached_reused += 1
                continue
            if card_png is None:
                continue
            message = await bot.send_photo(
                chat_id=recipient.chat_id,
                photo=BufferedInputFile(
                    card_png,
                    filename=f"duel_{context.challenge_id}_{recipient.role}.png",
                ),
                caption=caption,
                reply_markup=keyboard,
            )
            sent += 1
            if not message.photo:
                continue
            file_id = message.photo[-1].file_id
            if recipient.role == "creator":
                new_creator_file_id = file_id
            else:
                new_opponent_file_id = file_id
    except Exception as exc:
        logger.warning(
            "friend_challenge_proof_card_send_failed",
            challenge_id=context.challenge_id,
            error_type=type(exc).__name__,
        )
    finally:
        await bot.session.close()

    return FriendChallengeProofCardsDeliveryResult(
        sent=sent,
        cached_reused=cached_reused,
        new_creator_file_id=new_creator_file_id,
        new_opponent_file_id=new_opponent_file_id,
    )


__all__ = [
    "FriendChallengeProofCardsDeliveryResult",
    "deliver_friend_challenge_proof_cards",
]
