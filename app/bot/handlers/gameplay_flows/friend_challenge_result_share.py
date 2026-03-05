from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.keyboards.friend_challenge import build_friend_challenge_share_url
from app.bot.texts.de import TEXTS_DE
from app.core.telegram_links import public_bot_link


async def build_result_share_url(*, callback: CallbackQuery, proof_card_text: str) -> str | None:
    bot = callback.bot
    if bot is None:
        return None
    try:
        await bot.get_me()
    except Exception:
        return None
    return build_friend_challenge_share_url(
        base_link=public_bot_link(),
        share_text="\n".join(
            [
                proof_card_text,
                "",
                TEXTS_DE["msg.friend.challenge.proof.share.cta"],
            ]
        ),
    )
