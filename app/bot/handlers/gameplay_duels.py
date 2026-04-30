from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.keyboards.duels import (
    build_arena_create_keyboard,
    build_arena_empty_keyboard,
    build_duels_menu_keyboard,
    build_friend_duel_keyboard,
)
from app.bot.texts.de import TEXTS_DE
from app.game.duels.constants import (
    ARENA_CREATE_CALLBACK,
    ARENA_LIST_CALLBACK,
    ARENA_START_CREATE_CALLBACK,
    DUEL_ARENA_CALLBACK,
    DUEL_FRIEND_CALLBACK,
    DUEL_MENU_CALLBACK,
)


async def handle_duels_menu(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.menu"],
        reply_markup=build_duels_menu_keyboard(),
    )
    await callback.answer()


async def handle_arena_open(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.arena.empty"],
        reply_markup=build_arena_empty_keyboard(),
    )
    await callback.answer()


async def handle_arena_create(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.arena.create"],
        reply_markup=build_arena_create_keyboard(),
    )
    await callback.answer()


async def handle_arena_start_create(callback: CallbackQuery) -> None:
    await callback.answer(TEXTS_DE["msg.duels.arena.not_active"], show_alert=True)


async def handle_friend_duel_open(callback: CallbackQuery) -> None:
    if callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.friend"],
        reply_markup=build_friend_duel_keyboard(),
    )
    await callback.answer()


def register(router: Router) -> None:
    router.callback_query(F.data == DUEL_MENU_CALLBACK)(handle_duels_menu)
    router.callback_query((F.data == DUEL_ARENA_CALLBACK) | (F.data == ARENA_LIST_CALLBACK))(
        handle_arena_open
    )
    router.callback_query(F.data == ARENA_CREATE_CALLBACK)(handle_arena_create)
    router.callback_query(F.data == ARENA_START_CREATE_CALLBACK)(handle_arena_start_create)
    router.callback_query(F.data == DUEL_FRIEND_CALLBACK)(handle_friend_duel_open)
