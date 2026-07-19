from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.game.arena_duels.analytics import ArenaPaywallContext
from app.game.duels.constants import (
    ARENA_LIST_CALLBACK,
    DUEL_MENU_CALLBACK,
    DUEL_PAYWALL_CALLBACK_CONTEXT,
    DUEL_PAYWALL_PRODUCT_CODES,
    FRIEND_DUEL_CREATE_CALLBACK,
)


def build_duel_monetization_rows(
    *,
    paywall_context: ArenaPaywallContext,
) -> list[list[InlineKeyboardButton]]:
    ticket_product_code, premium_week_product_code = DUEL_PAYWALL_PRODUCT_CODES
    return [
        [
            InlineKeyboardButton(
                text="🎟 Revanche-Ticket – 5⭐",
                callback_data=_duel_paywall_buy_callback(
                    product_code=ticket_product_code,
                    paywall_context=paywall_context,
                ),
            )
        ],
        [
            InlineKeyboardButton(
                text="💎 Arena Pass 7 Tage – 29⭐",
                callback_data=_duel_paywall_buy_callback(
                    product_code=premium_week_product_code,
                    paywall_context=paywall_context,
                ),
            )
        ],
    ]


def build_duel_paywall_keyboard(
    *,
    paywall_context: ArenaPaywallContext,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *build_duel_monetization_rows(paywall_context=paywall_context),
            [InlineKeyboardButton(text="↩️ Später", callback_data=ARENA_LIST_CALLBACK)],
        ]
    )


def build_friend_duel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚔️ Freundesduell erstellen",
                    callback_data=FRIEND_DUEL_CREATE_CALLBACK,
                )
            ],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data=DUEL_MENU_CALLBACK)],
        ]
    )


def _duel_paywall_buy_callback(
    *,
    product_code: str,
    paywall_context: ArenaPaywallContext,
) -> str:
    return f"buy:{product_code}:{DUEL_PAYWALL_CALLBACK_CONTEXT}:{paywall_context}"
