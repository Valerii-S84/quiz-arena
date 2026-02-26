from __future__ import annotations

import re
from datetime import datetime, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.handlers.referral_views import _build_claim_status_text, _build_overview_text
from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.referral import (
    build_referral_keyboard,
    build_referral_share_keyboard,
    build_referral_share_url,
)
from app.bot.texts.de import TEXTS_DE
from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.session import SessionLocal
from app.economy.referrals.service import ReferralOverview, ReferralService
from app.services.user_onboarding import UserOnboardingService

router = Router(name="referral")

REWARD_CHOICE_RE = re.compile(r"^referral:reward:(MEGA_PACK_15|PREMIUM_STARTER)$")
SHARE_RE = re.compile(r"^referral:(share|prompt:share)$")


async def _build_invite_link(bot: Bot, *, referral_code: str) -> str | None:
    try:
        me = await bot.get_me()
    except Exception:
        return None
    if not me.username:
        return None
    return f"https://t.me/{me.username}?start=ref_{referral_code}"


async def _load_overview(
    *,
    telegram_user: TelegramUser,
    now_utc: datetime,
) -> ReferralOverview | None:
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=telegram_user,
        )
        return await ReferralService.get_referrer_overview(
            session,
            user_id=snapshot.user_id,
            now_utc=now_utc,
        )


@router.message(Command("referral", "invite"))
async def handle_referral_command(message: Message) -> None:
    if message.from_user is None:
        await message.answer(TEXTS_DE["msg.system.error"], reply_markup=build_home_keyboard())
        return

    now_utc = datetime.now(timezone.utc)
    overview = await _load_overview(telegram_user=message.from_user, now_utc=now_utc)
    if overview is None:
        await message.answer(TEXTS_DE["msg.system.error"], reply_markup=build_home_keyboard())
        return

    invite_link = await _build_invite_link(message.bot, referral_code=overview.referral_code)
    await message.answer(
        _build_overview_text(overview=overview, invite_link=invite_link),
        reply_markup=build_referral_keyboard(
            invite_link=invite_link,
            has_claimable_reward=overview.claimable_rewards > 0,
        ),
    )


@router.callback_query(F.data == "referral:open")
async def handle_referral_open(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    overview = await _load_overview(telegram_user=callback.from_user, now_utc=now_utc)
    if overview is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    invite_link = await _build_invite_link(callback.bot, referral_code=overview.referral_code)
    await callback.message.answer(
        _build_overview_text(overview=overview, invite_link=invite_link),
        reply_markup=build_referral_keyboard(
            invite_link=invite_link,
            has_claimable_reward=overview.claimable_rewards > 0,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(REWARD_CHOICE_RE))
async def handle_referral_reward_choice(callback: CallbackQuery) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    matched = REWARD_CHOICE_RE.match(callback.data)
    if matched is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    reward_code = matched.group(1)

    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        claim = await ReferralService.claim_next_reward_choice(
            session,
            user_id=snapshot.user_id,
            reward_code=reward_code,
            now_utc=now_utc,
        )
        if claim is not None and claim.status == "CLAIMED" and claim.reward_code is not None:
            await emit_analytics_event(
                session,
                event_type="referral_reward_claimed",
                source=EVENT_SOURCE_BOT,
                happened_at=now_utc,
                user_id=snapshot.user_id,
                payload={"reward_code": claim.reward_code},
            )

    if claim is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    invite_link = await _build_invite_link(callback.bot, referral_code=claim.overview.referral_code)
    response_text = "\n".join(
        [
            _build_claim_status_text(claim),
            _build_overview_text(overview=claim.overview, invite_link=invite_link),
        ]
    )
    await callback.message.answer(
        response_text,
        reply_markup=build_referral_keyboard(
            invite_link=invite_link,
            has_claimable_reward=claim.overview.claimable_rewards > 0,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(SHARE_RE))
async def handle_referral_share(callback: CallbackQuery) -> None:
    if callback.data is None or callback.from_user is None or callback.message is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    overview = await _load_overview(telegram_user=callback.from_user, now_utc=now_utc)
    if overview is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    invite_link = await _build_invite_link(callback.bot, referral_code=overview.referral_code)
    if invite_link is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    share_url = build_referral_share_url(
        invite_link=invite_link,
        share_text=TEXTS_DE["msg.referral.share.cta"],
    )
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        await emit_analytics_event(
            session,
            event_type="referral_link_shared",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=snapshot.user_id,
            payload={"entrypoint": callback.data},
        )

    await callback.message.answer(
        TEXTS_DE["msg.referral.share.ready"],
        reply_markup=build_referral_share_keyboard(share_url=share_url),
    )
    await callback.answer()


@router.callback_query(F.data == "referral:prompt:later")
async def handle_referral_prompt_later(callback: CallbackQuery) -> None:
    await callback.answer()
