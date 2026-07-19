from __future__ import annotations

from typing import Literal

from aiogram.types import CallbackQuery

from app.bot.keyboards.duels import build_duel_paywall_keyboard
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.analytics import ArenaPaywallContext

DuelPaywallContext = Literal[
    "close_loss",
    "revanche_limit",
    "arena_limit",
    "friend_create_limit",
    "friend_rematch_limit",
    "beaten_result",
]

DUEL_PAYWALL_TEXT_KEYS: dict[DuelPaywallContext, str] = {
    "close_loss": "msg.duels.paywall.close_loss",
    "revanche_limit": "msg.duels.paywall.revanche_limit",
    "arena_limit": "msg.duels.paywall.arena_limit",
    "friend_create_limit": "msg.duels.paywall.friend_create_limit",
    "friend_rematch_limit": "msg.duels.paywall.friend_rematch_limit",
    "beaten_result": "msg.duels.paywall.beaten_result",
}


def resolve_duel_paywall_text(*, context: DuelPaywallContext) -> str:
    return TEXTS_DE[DUEL_PAYWALL_TEXT_KEYS[context]]


async def send_duel_paywall(callback: CallbackQuery, *, context: DuelPaywallContext) -> None:
    if callback.message is not None:
        await callback.message.answer(
            resolve_duel_paywall_text(context=context),
            reply_markup=build_duel_paywall_keyboard(
                paywall_context=_paywall_context_for_text_context(context)
            ),
        )
    await callback.answer()


def _paywall_context_for_text_context(context: DuelPaywallContext) -> ArenaPaywallContext:
    return context
