from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.promo import build_promo_discount_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.economy.promo.errors import (
    PromoAlreadyUsedError,
    PromoExpiredError,
    PromoIdempotencyConflictError,
    PromoInvalidError,
    PromoNotApplicableError,
    PromoRateLimitedError,
)
from app.economy.promo.service import PromoService
from app.services.user_onboarding import UserOnboardingService

router = Router(name="promo")


@router.callback_query(F.data == "promo:open")
async def handle_promo_open(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.answer(TEXTS_DE["msg.promo.input.hint"], reply_markup=build_home_keyboard())
    await callback.answer()


@router.message(Command("promo"))
async def handle_promo_command(message: Message) -> None:
    if message.from_user is None:
        await message.answer(TEXTS_DE["msg.system.error"], reply_markup=build_home_keyboard())
        return

    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(TEXTS_DE["msg.promo.input.hint"], reply_markup=build_home_keyboard())
        return
    promo_code = parts[1].strip()

    now_utc = datetime.now(timezone.utc)

    try:
        async with SessionLocal.begin() as session:
            snapshot = await UserOnboardingService.ensure_home_snapshot(
                session,
                telegram_user=message.from_user,
            )
            result = await PromoService.redeem(
                session,
                user_id=snapshot.user_id,
                promo_code=promo_code,
                idempotency_key=f"promo:{snapshot.user_id}:{message.message_id}",
                now_utc=now_utc,
            )
    except PromoInvalidError:
        await message.answer(TEXTS_DE["msg.promo.error.invalid"], reply_markup=build_home_keyboard())
        return
    except PromoExpiredError:
        await message.answer(TEXTS_DE["msg.promo.error.expired"], reply_markup=build_home_keyboard())
        return
    except (PromoAlreadyUsedError, PromoIdempotencyConflictError):
        await message.answer(TEXTS_DE["msg.promo.error.used"], reply_markup=build_home_keyboard())
        return
    except PromoNotApplicableError:
        await message.answer(TEXTS_DE["msg.promo.error.not_applicable"], reply_markup=build_home_keyboard())
        return
    except PromoRateLimitedError:
        await message.answer(TEXTS_DE["msg.promo.error.rate_limited"], reply_markup=build_home_keyboard())
        return

    if result.result_type == "PREMIUM_GRANT":
        await message.answer(TEXTS_DE["msg.promo.success.grant"], reply_markup=build_home_keyboard())
        return

    discount_keyboard = build_promo_discount_keyboard(
        redemption_id=result.redemption_id,
        target_scope=result.target_scope,
        discount_percent=result.discount_percent,
    )
    await message.answer(
        TEXTS_DE["msg.promo.success.discount"],
        reply_markup=discount_keyboard or build_home_keyboard(),
    )
