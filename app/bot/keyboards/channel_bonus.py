from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_channel_bonus_keyboard(*, channel_url: str | None) -> InlineKeyboardMarkup:
    channel_button: InlineKeyboardButton
    if channel_url:
        channel_button = InlineKeyboardButton(text="📺 Zum Kanal →", url=channel_url)
    else:
        channel_button = InlineKeyboardButton(
            text="📺 Zum Kanal →",
            callback_data="channel_bonus:channel_unavailable",
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [channel_button],
            [InlineKeyboardButton(text="✅ Ich habe abonniert", callback_data="channel_bonus:check")],
        ]
    )
