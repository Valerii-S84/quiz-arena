from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_views import _format_user_label
from app.bot.keyboards.duels import (
    build_arena_expired_guard_keyboard,
    build_arena_guard_back_keyboard,
    build_duel_paywall_keyboard,
)
from app.bot.texts.de import TEXTS_DE
from app.game.arena_duels.types import ArenaBaselineStartResult, ArenaChallengerStartResult
from app.game.sessions.types import StartSessionResult

DuelPaywallContext = Literal[
    "close_loss",
    "revanche_limit",
    "arena_accept_limit",
    "friend_limit",
    "beaten_result",
]

DUEL_PAYWALL_TEXT_KEYS: dict[DuelPaywallContext, str] = {
    "close_loss": "msg.duels.paywall.close_loss",
    "revanche_limit": "msg.duels.paywall.revanche_limit",
    "arena_accept_limit": "msg.duels.paywall.arena_accept_limit",
    "friend_limit": "msg.duels.paywall.friend_limit",
    "beaten_result": "msg.duels.paywall.beaten_result",
}


def extract_start_result(result: object | None) -> StartSessionResult | None:
    if result is None:
        return None
    if isinstance(result, ArenaBaselineStartResult):
        return result.start_result
    if isinstance(result, ArenaChallengerStartResult):
        return result.start_result
    return getattr(result, "start_result", None)


def parse_arena_duel_id(callback: CallbackQuery, *, pattern, parse_uuid_callback) -> UUID | None:
    if callback.data is None:
        return None
    return parse_uuid_callback(pattern=pattern, callback_data=callback.data)


def format_score_line(*, score: int, time_ms: int) -> str:
    total_seconds = max(0, int(round(time_ms / 1000)))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{score}/7 · {minutes:02d}:{seconds:02d}"


async def resolve_arena_user_label(*, session, user_onboarding_service, user_id: int) -> str:
    user = await user_onboarding_service.get_by_id(session, user_id)
    if user is None:
        return f"Spieler #{user_id}"
    return _format_user_label(
        username=user.username,
        first_name=user.first_name,
        fallback=f"Spieler #{user_id}",
    )


def build_arena_guard_keyboard(text_key: str) -> object:
    if text_key == "msg.duels.arena.expired":
        return build_arena_expired_guard_keyboard()
    return build_arena_guard_back_keyboard()


async def send_arena_guard(callback: CallbackQuery, *, text_key: str, reply_markup) -> None:
    if callback.message is not None:
        await callback.message.answer(TEXTS_DE[text_key], reply_markup=reply_markup)
    await callback.answer()


def resolve_duel_paywall_text(*, context: DuelPaywallContext) -> str:
    return TEXTS_DE[DUEL_PAYWALL_TEXT_KEYS[context]]


async def send_duel_paywall(callback: CallbackQuery, *, context: DuelPaywallContext) -> None:
    if callback.message is not None:
        await callback.message.answer(
            resolve_duel_paywall_text(context=context),
            reply_markup=build_duel_paywall_keyboard(),
        )
    await callback.answer()
