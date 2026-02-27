from __future__ import annotations

from datetime import datetime

from aiogram.types import CallbackQuery

from app.bot.keyboards.channel_bonus import build_channel_bonus_keyboard
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.offers import build_offer_keyboard
from app.bot.texts.de import TEXTS_DE
from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.economy.energy.constants import FREE_ENERGY_CAP


async def handle_energy_insufficient(
    callback: CallbackQuery,
    *,
    session,
    user_id: int,
    now_utc: datetime,
    offer_service,
    offer_logging_error,
    offer_idempotency_key: str,
    channel_bonus_service,
) -> None:
    message = callback.message
    if message is None:
        return

    if await channel_bonus_service.can_show_prompt(session, user_id=user_id):
        await emit_analytics_event(
            session,
            event_type="channel_bonus_shown",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=user_id,
            payload={"source": "energy_zero"},
        )
        await message.answer(
            TEXTS_DE["msg.channel.bonus.offer"].format(max_energy=FREE_ENERGY_CAP),
            reply_markup=build_channel_bonus_keyboard(
                channel_url=channel_bonus_service.resolve_channel_url(),
            ),
        )
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
