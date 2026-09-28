from __future__ import annotations

from datetime import datetime

from aiogram.types import CallbackQuery

from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.offers import build_offer_keyboard
from app.bot.texts.de import TEXTS_DE


async def handle_energy_insufficient(
    callback: CallbackQuery,
    *,
    session,
    user_id: int,
    now_utc: datetime,
    offer_service,
    offer_logging_error,
    offer_idempotency_key: str,
) -> None:
    message = callback.message
    if message is None:
        return

    offer_selection = None
    try:
        offer_selection = await offer_service.evaluate_and_log_offer(
            session,
            user_id=user_id,
            idempotency_key=offer_idempotency_key,
            now_utc=now_utc,
        )
    except offer_logging_error:
        offer_selection = None

    text = (
        TEXTS_DE[offer_selection.text_key]
        if offer_selection is not None
        else TEXTS_DE["msg.energy.empty.body"]
    )
    keyboard = (
        build_offer_keyboard(offer_selection)
        if offer_selection is not None
        else build_home_keyboard()
    )
    await message.answer(text, reply_markup=keyboard)
