from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards import duels_access
from app.game.duels.constants import (
    ARENA_ACCEPT_CALLBACK_PREFIX,
    ARENA_CHALLENGE_FRIEND_CALLBACK_PREFIX,
    ARENA_CREATE_CALLBACK,
    ARENA_LIST_CALLBACK,
    ARENA_START_ATTEMPT_CALLBACK_PREFIX,
    ARENA_START_CREATE_CALLBACK,
    DUEL_ARENA_CALLBACK,
    DUEL_FRIEND_CALLBACK,
    DUEL_MENU_CALLBACK,
)

ARENA_REVANCHE_CALLBACK_PREFIX = "arena:revanche:"
ARENA_REVANCHE_SEND_CALLBACK_PREFIX = "arena:revanche_send:"


@dataclass(frozen=True, slots=True)
class ArenaDuelButton:
    duel_id: str
    label: str
    marker: str


build_duel_paywall_keyboard = duels_access.build_duel_paywall_keyboard
build_friend_duel_keyboard = duels_access.build_friend_duel_keyboard


def build_duels_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏟 Offene Arena", callback_data=DUEL_ARENA_CALLBACK)],
            [InlineKeyboardButton(text="👤 Freundesduell", callback_data=DUEL_FRIEND_CALLBACK)],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
        ]
    )


def build_arena_list_keyboard(*, duels: tuple[ArenaDuelButton, ...]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{duel.marker} {duel.label} schlagen",
                callback_data=f"{ARENA_ACCEPT_CALLBACK_PREFIX}{duel.duel_id}",
            )
        ]
        for duel in duels
    ]
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🎯 Eigenes Arena-Duell erstellen", callback_data=ARENA_CREATE_CALLBACK
                )
            ],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data=DUEL_MENU_CALLBACK)],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_arena_empty_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎯 Erstes Arena-Duell erstellen",
                    callback_data=ARENA_CREATE_CALLBACK,
                )
            ],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data=DUEL_MENU_CALLBACK)],
        ]
    )


def build_arena_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Zur Arena", callback_data=ARENA_LIST_CALLBACK)],
        ]
    )


def build_arena_expired_guard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎯 Eigenes Arena-Duell erstellen",
                    callback_data=ARENA_CREATE_CALLBACK,
                )
            ],
            [InlineKeyboardButton(text="🏟 Zur Arena", callback_data=ARENA_LIST_CALLBACK)],
        ]
    )


def build_arena_guard_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏟 Zur Arena", callback_data=ARENA_LIST_CALLBACK)],
        ]
    )


def build_arena_accept_keyboard(*, duel_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="▶️ Starten",
                    callback_data=f"{ARENA_START_ATTEMPT_CALLBACK_PREFIX}{duel_id}",
                )
            ],
            [InlineKeyboardButton(text="↩️ Zur Arena", callback_data=ARENA_LIST_CALLBACK)],
        ]
    )


def build_arena_create_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Starten", callback_data=ARENA_START_CREATE_CALLBACK)],
            [InlineKeyboardButton(text="↩️ Zur Arena", callback_data=ARENA_LIST_CALLBACK)],
        ]
    )


def build_arena_published_keyboard(*, duel_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👤 Freund herausfordern",
                    callback_data=f"{ARENA_CHALLENGE_FRIEND_CALLBACK_PREFIX}{duel_id}",
                )
            ],
            [InlineKeyboardButton(text="🏟 Zur Arena", callback_data=ARENA_LIST_CALLBACK)],
        ]
    )


def build_arena_result_keyboard(
    *,
    user_won: bool,
    revanche_attempt_id: str | None = None,
    close_loss: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    if revanche_attempt_id is not None and (user_won or close_loss):
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔁 Revanche",
                    callback_data=f"{ARENA_REVANCHE_CALLBACK_PREFIX}{revanche_attempt_id}",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🎯 Eigenes Arena-Duell erstellen",
                    callback_data=ARENA_CREATE_CALLBACK,
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🏟 Zur Arena", callback_data=ARENA_LIST_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_arena_revanche_confirm_keyboard(*, source_attempt_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔁 Revanche senden",
                    callback_data=f"{ARENA_REVANCHE_SEND_CALLBACK_PREFIX}{source_attempt_id}",
                )
            ],
            [InlineKeyboardButton(text="🏟 Zur Arena", callback_data=ARENA_LIST_CALLBACK)],
        ]
    )
