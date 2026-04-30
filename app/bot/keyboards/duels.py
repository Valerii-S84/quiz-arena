from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.game.duels.constants import (
    ARENA_CREATE_CALLBACK,
    ARENA_LIST_CALLBACK,
    ARENA_START_CREATE_CALLBACK,
    DUEL_ARENA_CALLBACK,
    DUEL_FRIEND_CALLBACK,
    DUEL_MENU_CALLBACK,
    FRIEND_DUEL_CREATE_CALLBACK,
)


def build_duels_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏟 Offene Arena", callback_data=DUEL_ARENA_CALLBACK)],
            [InlineKeyboardButton(text="👤 Freundesduell", callback_data=DUEL_FRIEND_CALLBACK)],
            [InlineKeyboardButton(text="↩️ Zurück", callback_data="home:open")],
        ]
    )


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


def build_arena_create_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Starten", callback_data=ARENA_START_CREATE_CALLBACK)],
            [InlineKeyboardButton(text="↩️ Zur Arena", callback_data=ARENA_LIST_CALLBACK)],
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
