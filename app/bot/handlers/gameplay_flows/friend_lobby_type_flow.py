from __future__ import annotations

from aiogram.types import CallbackQuery

from app.bot.keyboards.duels import build_friend_duel_keyboard
from app.bot.keyboards.tournament import build_tournament_format_keyboard
from app.bot.texts.de import TEXTS_DE


async def handle_friend_challenge_type_selected(
    callback: CallbackQuery,
    *,
    friend_create_type_re,
) -> None:
    if callback.data is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    matched = friend_create_type_re.match(callback.data)
    if matched is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    selected_type = matched.group(1)
    if selected_type == "tournament":
        await callback.message.answer(
            TEXTS_DE["msg.friend.challenge.tournament.format"],
            reply_markup=build_tournament_format_keyboard(),
        )
        await callback.answer()
        return
    await callback.message.answer(
        TEXTS_DE["msg.duels.friend"],
        reply_markup=build_friend_duel_keyboard(challenge_type=selected_type),
    )
    await callback.answer()
