from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, User as TelegramUser

from app.bot.keyboards.home import build_home_keyboard
from app.bot.keyboards.referral import build_referral_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.session import SessionLocal
from app.economy.energy.constants import BERLIN_TIMEZONE
from app.economy.referrals.constants import REWARD_CODE_MEGA_PACK
from app.economy.referrals.service import ReferralClaimResult, ReferralOverview, ReferralService
from app.services.user_onboarding import UserOnboardingService

router = Router(name="referral")

REWARD_CHOICE_RE = re.compile(r"^referral:reward:(MEGA_PACK_15|PREMIUM_STARTER)$")


def _format_berlin_time(at_utc: datetime) -> str:
    return at_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).strftime("%d.%m %H:%M")


async def _build_invite_link(bot: Bot, *, referral_code: str) -> str | None:
    try:
        me = await bot.get_me()
    except Exception:
        return None
    if not me.username:
        return None
    return f"https://t.me/{me.username}?start=ref_{referral_code}"


def _build_overview_text(*, overview: ReferralOverview, invite_link: str | None) -> str:
    lines = [
        TEXTS_DE["msg.referral.invite"],
        TEXTS_DE["msg.referral.progress"].format(qualified=overview.progress_qualified),
    ]

    if invite_link:
        lines.append(TEXTS_DE["msg.referral.link"])
    else:
        lines.append(TEXTS_DE["msg.referral.link.fallback"].format(referral_code=overview.referral_code))

    if overview.pending_rewards_total > 0:
        lines.append(
            TEXTS_DE["msg.referral.pending"].format(
                pending=overview.pending_rewards_total,
                claimable=overview.claimable_rewards,
            )
        )

    if overview.claimable_rewards > 0:
        lines.append(TEXTS_DE["msg.referral.reward.choice"])
    elif overview.next_reward_at_utc is not None:
        lines.append(
            TEXTS_DE["msg.referral.next_reward_at"].format(
                next_reward_at=_format_berlin_time(overview.next_reward_at_utc)
            )
        )
    elif overview.deferred_rewards > 0:
        lines.append(TEXTS_DE["msg.referral.reward.monthly_cap"])

    return "\n".join(lines)


def _build_claim_status_text(claim: ReferralClaimResult) -> str:
    if claim.status == "CLAIMED":
        if claim.reward_code == REWARD_CODE_MEGA_PACK:
            return TEXTS_DE["msg.referral.reward.claimed.megapack"]
        return TEXTS_DE["msg.referral.reward.claimed.premium"]
    if claim.status == "TOO_EARLY":
        return TEXTS_DE["msg.referral.reward.too_early"]
    if claim.status == "MONTHLY_CAP":
        return TEXTS_DE["msg.referral.reward.monthly_cap"]
    return TEXTS_DE["msg.referral.reward.unavailable"]


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
