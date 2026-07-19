from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.handlers.promo_input import mark_promo_waiting_started
from app.bot.keyboards.promo import build_promo_input_keyboard
from app.bot.texts.de import TEXTS_DE


async def prompt_for_promo_input(message: Message, state: FSMContext | None = None) -> None:
    if state is not None:
        await mark_promo_waiting_started(state)
    await message.answer(
        TEXTS_DE["msg.promo.input.hint"],
        reply_markup=build_promo_input_keyboard(),
    )
