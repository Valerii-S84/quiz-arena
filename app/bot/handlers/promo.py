from __future__ import annotations

import re
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, ForceReply, Message

from app.bot.keyboards.promo import build_promo_discount_keyboard
from app.bot.keyboards.shop import build_shop_keyboard
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
PROMO_INPUT_RE = re.compile(r"^/?promo\s+(.+)$", re.IGNORECASE)
PROMO_STANDALONE_PATTERN = r"(?i)^(?=.*[-\d])[A-Z0-9][A-Z0-9_-]{3,39}$"
PROMO_STANDALONE_RE = re.compile(PROMO_STANDALONE_PATTERN)


def _is_reply_to_promo_prompt(message: Message) -> bool:
    if message.reply_to_message is None or message.reply_to_message.from_user is None:
        return False
    if not message.reply_to_message.from_user.is_bot:
        return False
    reply_text = message.reply_to_message.text or ""
    return reply_text.startswith(TEXTS_DE["msg.promo.reply_prefix"])


def _extract_promo_code(message: Message) -> str | None:
    text = (message.text or "").strip()
    if not text:
        return None

    match = PROMO_INPUT_RE.match(text)
    if match is not None:
        promo_code = match.group(1).strip()
        return promo_code or None

    if _is_reply_to_promo_prompt(message):
        return text

    if PROMO_STANDALONE_RE.fullmatch(text):
        return text

    return None


async def _prompt_for_promo_input(message: Message) -> None:
    await message.answer(
        TEXTS_DE["msg.promo.input.hint"],
        reply_markup=ForceReply(selective=True, input_field_placeholder="WILLKOMMEN-50"),
    )


@router.callback_query(F.data == "promo:open")
async def handle_promo_open(callback: CallbackQuery) -> None:
    if callback.message is not None:
        await _prompt_for_promo_input(callback.message)
    await callback.answer()


@router.message(Command("promo"))
async def handle_promo_command(message: Message) -> None:
    await _redeem_promo_from_text(message)


@router.message(F.text.regexp(r"(?i)^promo\s+"))
async def handle_promo_text(message: Message) -> None:
    await _redeem_promo_from_text(message)


@router.message(F.text.regexp(PROMO_STANDALONE_PATTERN))
async def handle_promo_plain_code(message: Message) -> None:
    await _redeem_promo_from_text(message)


@router.message(F.reply_to_message)
async def handle_promo_reply(message: Message) -> None:
    if not _is_reply_to_promo_prompt(message):
        return
    await _redeem_promo_from_text(message)


async def _redeem_promo_from_text(message: Message) -> None:
    if message.from_user is None:
        await message.answer(TEXTS_DE["msg.system.error"], reply_markup=build_shop_keyboard())
        return

    promo_code = _extract_promo_code(message)
    if promo_code is None:
        await _prompt_for_promo_input(message)
        return

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
        await message.answer(TEXTS_DE["msg.promo.error.invalid"], reply_markup=build_shop_keyboard())
        return
    except PromoExpiredError:
        await message.answer(TEXTS_DE["msg.promo.error.expired"], reply_markup=build_shop_keyboard())
        return
    except (PromoAlreadyUsedError, PromoIdempotencyConflictError):
        await message.answer(TEXTS_DE["msg.promo.error.used"], reply_markup=build_shop_keyboard())
        return
    except PromoNotApplicableError:
        await message.answer(TEXTS_DE["msg.promo.error.not_applicable"], reply_markup=build_shop_keyboard())
        return
    except PromoRateLimitedError:
        await message.answer(TEXTS_DE["msg.promo.error.rate_limited"], reply_markup=build_shop_keyboard())
        return

    if result.result_type == "PREMIUM_GRANT":
        await message.answer(TEXTS_DE["msg.promo.success.grant"], reply_markup=build_shop_keyboard())
        return

    discount_keyboard = build_promo_discount_keyboard(
        redemption_id=result.redemption_id,
        target_scope=result.target_scope,
        discount_percent=result.discount_percent,
    )
    await message.answer(
        TEXTS_DE["msg.promo.success.discount"],
        reply_markup=discount_keyboard or build_shop_keyboard(),
    )
