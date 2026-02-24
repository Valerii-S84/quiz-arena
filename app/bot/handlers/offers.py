from __future__ import annotations

import re
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.economy.offers.service import OfferService
from app.services.user_onboarding import UserOnboardingService

router = Router(name="offers")

DISMISS_RE = re.compile(r"^offer:dismiss:(\d+)$")


@router.callback_query(F.data.regexp(DISMISS_RE))
async def handle_offer_dismiss(callback: CallbackQuery) -> None:
    if callback.data is None or callback.from_user is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    matched = DISMISS_RE.match(callback.data)
    if matched is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    impression_id = int(matched.group(1))
    now_utc = datetime.now(timezone.utc)

    async with SessionLocal.begin() as session:
        user = await UserOnboardingService.get_by_telegram_user_id(session, callback.from_user.id)
        if user is None:
            await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
            return

        dismissed = await OfferService.dismiss_offer(
            session,
            user_id=user.id,
            impression_id=impression_id,
            now_utc=now_utc,
        )

    if dismissed:
        await callback.answer(TEXTS_DE["msg.offer.dismissed"])
        return

    await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
