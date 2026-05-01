from __future__ import annotations

from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.game.duels.constants import (
    ARENA_ACCEPT_CALLBACK_PREFIX,
    ARENA_CREATE_CALLBACK,
    ARENA_LIST_CALLBACK,
    ARENA_START_ATTEMPT_CALLBACK_PREFIX,
    ARENA_START_CREATE_CALLBACK,
    DUEL_ARENA_CALLBACK,
    DUEL_FRIEND_CALLBACK,
    DUEL_MENU_CALLBACK,
    DUEL_PAYWALL_PRODUCT_CODES,
    FRIEND_DUEL_CREATE_CALLBACK,
)


@dataclass(frozen=True, slots=True)
class ArenaDuelButton:
    duel_id: str
    label: str
    marker: str


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


def build_arena_published_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏟 Zur Arena", callback_data=ARENA_LIST_CALLBACK)],
            [
                InlineKeyboardButton(
                    text="👤 Freund herausfordern", callback_data=DUEL_FRIEND_CALLBACK
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Neues Arena-Duell erstellen",
                    callback_data=ARENA_CREATE_CALLBACK,
                )
            ],
        ]
    )


def build_arena_result_keyboard(*, user_won: bool) -> InlineKeyboardMarkup:
    rows = []
    if user_won:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🎯 Eigenes Arena-Duell erstellen",
                    callback_data=ARENA_CREATE_CALLBACK,
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🏟 Zur Arena", callback_data=ARENA_LIST_CALLBACK)])
    if not user_won:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🎯 Eigenes Arena-Duell erstellen",
                    callback_data=ARENA_CREATE_CALLBACK,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_duel_paywall_keyboard() -> InlineKeyboardMarkup:
    ticket_product_code, premium_week_product_code = DUEL_PAYWALL_PRODUCT_CODES
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎟 Duell-Ticket – 5⭐",
                    callback_data=f"buy:{ticket_product_code}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="👑 Premium-Woche – 29⭐",
                    callback_data=f"buy:{premium_week_product_code}",
                )
            ],
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
