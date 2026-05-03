from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.game.duels.constants import (
    ARENA_LIST_CALLBACK,
    DUEL_MENU_CALLBACK,
    DUEL_PAYWALL_CALLBACK_CONTEXT,
    DUEL_PAYWALL_PRODUCT_CODES,
)


def build_duel_paywall_keyboard() -> InlineKeyboardMarkup:
    ticket_product_code, premium_week_product_code = DUEL_PAYWALL_PRODUCT_CODES
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎟 Duell-Ticket – 5⭐",
                    callback_data=f"buy:{ticket_product_code}:{DUEL_PAYWALL_CALLBACK_CONTEXT}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👑 Premium-Woche – 29⭐",
                    callback_data=(
                        f"buy:{premium_week_product_code}:{DUEL_PAYWALL_CALLBACK_CONTEXT}"
                    ),
                )
            ],
            [InlineKeyboardButton(text="↩️ Später", callback_data=ARENA_LIST_CALLBACK)],
        ]
    )


def build_friend_duel_keyboard(*, challenge_type: str = "direct") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ Freundesduell erstellen",
                    callback_data=f"friend:challenge:format:{challenge_type}:7",
                )
            ],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data=DUEL_MENU_CALLBACK)],
        ]
    )
