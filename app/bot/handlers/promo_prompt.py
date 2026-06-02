from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.handlers.promo_input import PromoCode
from app.bot.keyboards.promo import build_promo_input_keyboard
from app.bot.texts.de import TEXTS_DE


async def prompt_for_promo_input(message: Message, state: FSMContext | None = None) -> None:
    if state is not None:
        await state.set_state(PromoCode.waiting_for_code)
    await message.answer(
        TEXTS_DE["msg.promo.input.hint"],
        reply_markup=build_promo_input_keyboard(),
    )
