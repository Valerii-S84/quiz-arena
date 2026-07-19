from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.handlers.promo_input import issue_promo_menu_nonce, remember_promo_menu_message_id
from app.bot.keyboards.shop import build_shop_keyboard
from app.bot.texts.de import TEXTS_DE


async def answer_shop_message(
    message: Message,
    *,
    state: FSMContext | None,
    text_key: str,
) -> None:
    promo_nonce = await issue_promo_menu_nonce(state)
    sent_message = await message.answer(
        TEXTS_DE[text_key],
        reply_markup=build_shop_keyboard(promo_nonce=promo_nonce),
    )
    await remember_promo_menu_message_id(state, sent_message)
