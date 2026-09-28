from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.handlers.promo_input import issue_promo_menu_nonce, remember_promo_menu_message_id
from app.bot.keyboards.shop import build_shop_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.services.user_onboarding import UserOnboardingService


async def handle_shop_open(
    callback: CallbackQuery,
    *,
    state: FSMContext | None = None,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    async with SessionLocal.begin() as session:
        await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

    promo_nonce = await issue_promo_menu_nonce(state)
    sent_message = await callback.message.answer(
        TEXTS_DE["msg.shop.title"],
        reply_markup=build_shop_keyboard(
            promo_nonce=promo_nonce,
        ),
    )
    await remember_promo_menu_message_id(state, sent_message)
    await callback.answer()
