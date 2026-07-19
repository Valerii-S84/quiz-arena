from __future__ import annotations

from datetime import datetime, timezone

from aiogram.fsm.context import FSMContext
from aiogram.types import Message, User

from app.bot.handlers.promo_input import extract_promo_code, resolve_attempt_source
from app.bot.handlers.promo_prompt import prompt_for_promo_input
from app.bot.handlers.promo_view_helpers import (
    format_berlin_time,
    resolve_discount_label,
    resolve_scope_label,
)
from app.bot.keyboards.promo import build_promo_discount_keyboard
from app.bot.promo_shop import answer_shop_message
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.economy.promo.errors import (
    PromoAlreadyUsedError,
    PromoError,
    PromoExpiredError,
    PromoIdempotencyConflictError,
    PromoInvalidError,
    PromoNotApplicableError,
    PromoRateLimitedError,
)
from app.economy.promo.service import PromoService
from app.economy.promo.types import PromoRedeemResult
from app.services.user_onboarding import UserOnboardingService

_PROMO_ERRORS = (
    PromoInvalidError,
    PromoExpiredError,
    PromoAlreadyUsedError,
    PromoIdempotencyConflictError,
    PromoNotApplicableError,
    PromoRateLimitedError,
)
_PROMO_ERROR_TEXT_KEYS = {
    PromoInvalidError: "msg.promo.error.invalid",
    PromoExpiredError: "msg.promo.error.expired",
    PromoAlreadyUsedError: "msg.promo.error.used",
    PromoIdempotencyConflictError: "msg.promo.error.used",
    PromoNotApplicableError: "msg.promo.error.not_applicable",
    PromoRateLimitedError: "msg.promo.error.rate_limited",
}


async def redeem_promo_from_text(
    message: Message,
    *,
    state: FSMContext | None = None,
    allow_plain_text: bool = False,
    from_waiting_state: bool = False,
) -> None:
    telegram_user = message.from_user
    if telegram_user is None:
        await answer_shop_message(message, state=state, text_key="msg.system.error")
        return

    promo_code = extract_promo_code(message, allow_plain_text=allow_plain_text)
    if promo_code is None:
        await prompt_for_promo_input(message, state)
        return

    try:
        result = await _redeem_code(
            message,
            telegram_user=telegram_user,
            promo_code=promo_code,
            from_waiting_state=from_waiting_state,
        )
        if state is not None:
            await state.clear()
    except _PROMO_ERRORS as exc:
        await _answer_promo_error(message, state=state, error=exc)
        return

    await _answer_promo_success(message, state=state, result=result)


async def _redeem_code(
    message: Message,
    *,
    telegram_user: User,
    promo_code: str,
    from_waiting_state: bool,
) -> PromoRedeemResult:
    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
        )
        return await PromoService.redeem(
            session,
            user_id=snapshot.user_id,
            promo_code=promo_code,
            idempotency_key=f"promo:{snapshot.user_id}:{message.message_id}",
            source=resolve_attempt_source(
                message,
                from_waiting_state=from_waiting_state,
            ),
            now_utc=now_utc,
        )


async def _answer_promo_error(
    message: Message,
    *,
    state: FSMContext | None,
    error: PromoError,
) -> None:
    if state is not None:
        await state.clear()
    text_key = _PROMO_ERROR_TEXT_KEYS[type(error)]
    await answer_shop_message(message, state=state, text_key=text_key)


async def _answer_promo_success(
    message: Message,
    *,
    state: FSMContext | None,
    result: PromoRedeemResult,
) -> None:
    if result.result_type == "PREMIUM_GRANT":
        await answer_shop_message(message, state=state, text_key="msg.promo.success.grant")
        await message.answer(
            TEXTS_DE["msg.promo.success.grant.details"].format(
                premium_days=result.premium_days or 0,
                premium_ends_at=format_berlin_time(result.premium_ends_at),
            )
        )
        return

    discount_keyboard = build_promo_discount_keyboard(
        redemption_id=result.redemption_id,
        target_scope=result.target_scope,
        discount_type=result.discount_type,
        discount_value=result.discount_value,
        applicable_products=result.applicable_products,
    )
    if discount_keyboard is None:
        await answer_shop_message(
            message,
            state=state,
            text_key="msg.promo.discount.unavailable",
        )
        return

    await message.answer(
        TEXTS_DE["msg.promo.success.discount"],
        reply_markup=discount_keyboard,
    )
    await message.answer(
        TEXTS_DE["msg.promo.success.discount.details"].format(
            discount_label=resolve_discount_label(result),
            scope_label=resolve_scope_label(
                result.target_scope,
                applicable_products=result.applicable_products,
            ),
            reserved_until=format_berlin_time(result.reserved_until),
        )
    )
