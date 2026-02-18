from __future__ import annotations

import re
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.offers import build_offer_keyboard
from app.bot.keyboards.shop import build_shop_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.economy.offers.service import OfferLoggingError, OfferService
from app.services.user_onboarding import UserOnboardingService

router = Router(name="start")
START_PAYLOAD_RE = re.compile(r"^/start(?:@\w+)?(?:\s+(.+))?$")


def _extract_start_payload(text: str | None) -> str | None:
    if not text:
        return None
    matched = START_PAYLOAD_RE.match(text.strip())
    if matched is None:
        return None
    payload = matched.group(1)
    return payload.strip() if payload else None


def _build_home_text(*, free_energy: int, paid_energy: int, current_streak: int) -> str:
    return "\n".join(
        [
            TEXTS_DE["msg.home.title"],
            TEXTS_DE["msg.home.energy"].format(
                free_energy=free_energy,
                paid_energy=paid_energy,
            ),
            TEXTS_DE["msg.home.streak"].format(streak=current_streak),
            TEXTS_DE["msg.home.hint"],
        ]
    )


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    if message.from_user is None:
        await message.answer(TEXTS_DE["msg.system.error"])
        return

    now_utc = datetime.now(timezone.utc)
    offer_selection = None
    start_payload = _extract_start_payload(message.text)
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=message.from_user,
            start_payload=start_payload,
        )
        try:
            offer_selection = await OfferService.evaluate_and_log_offer(
                session,
                user_id=snapshot.user_id,
                idempotency_key=f"offer:start:{message.from_user.id}:{message.message_id}",
                now_utc=now_utc,
            )
        except OfferLoggingError:
            offer_selection = None

    response_text = _build_home_text(
        free_energy=snapshot.free_energy,
        paid_energy=snapshot.paid_energy,
        current_streak=snapshot.current_streak,
    )
    await message.answer(response_text, reply_markup=build_home_keyboard())
    if offer_selection is not None:
        await message.answer(
            TEXTS_DE[offer_selection.text_key],
            reply_markup=build_offer_keyboard(offer_selection),
        )


@router.callback_query(F.data == "shop:open")
async def handle_shop_open(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(TEXTS_DE["msg.shop.title"], reply_markup=build_shop_keyboard())
    await callback.answer()


@router.callback_query(F.data == "home:open")
async def handle_home_open(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )

    response_text = _build_home_text(
        free_energy=snapshot.free_energy,
        paid_energy=snapshot.paid_energy,
        current_streak=snapshot.current_streak,
    )
    await callback.message.answer(response_text, reply_markup=build_home_keyboard())
    await callback.answer()
