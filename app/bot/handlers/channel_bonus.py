from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.bot.handlers.channel_bonus_results import (
    answer_channel_bonus_result,
    emit_channel_bonus_check_started,
    emit_channel_bonus_result_event,
)
from app.bot.keyboards.channel_bonus import build_channel_bonus_keyboard
from app.bot.texts.de import TEXTS_DE
from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.session import SessionLocal
from app.economy.energy.constants import FREE_ENERGY_CAP
from app.services.channel_bonus import ChannelBonusService
from app.services.user_onboarding import UserOnboardingService

router = Router(name="channel_bonus")


def _channel_bonus_offer_text() -> str:
    return TEXTS_DE["msg.channel.bonus.offer"].format(max_energy=FREE_ENERGY_CAP)


async def _show_channel_bonus_offer(
    *,
    session,
    message: Message,
    user_id: int,
    now_utc: datetime,
    source: str,
) -> bool:
    if not await ChannelBonusService.can_show_prompt(session, user_id=user_id):
        return False

    await emit_analytics_event(
        session,
        event_type="channel_bonus_shown",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload={"source": source},
    )
    await message.answer(
        _channel_bonus_offer_text(),
        reply_markup=build_channel_bonus_keyboard(
            channel_url=ChannelBonusService.resolve_channel_url(),
        ),
    )
    return True


@router.callback_query(F.data == "channel_bonus:open")
async def handle_channel_bonus_open(callback: CallbackQuery) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        shown = await _show_channel_bonus_offer(
            session=session,
            message=callback.message,
            user_id=snapshot.user_id,
            now_utc=now_utc,
            source="shop",
        )

    if not shown:
        await callback.message.answer(TEXTS_DE["msg.channel.bonus.already_claimed"])
    await callback.answer()


@router.callback_query(F.data == "channel_bonus:check")
async def handle_channel_bonus_check(callback: CallbackQuery) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return
    bot = callback.bot
    if bot is None:
        await callback.answer(TEXTS_DE["msg.system.error"], show_alert=True)
        return

    now_utc = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        snapshot = await UserOnboardingService.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        await emit_channel_bonus_check_started(
            session,
            user_id=snapshot.user_id,
            now_utc=now_utc,
        )
        claim_result = await ChannelBonusService.claim_bonus_if_subscribed(
            session,
            user_id=snapshot.user_id,
            telegram_user_id=callback.from_user.id,
            bot=bot,
            now_utc=now_utc,
        )
        await emit_channel_bonus_result_event(
            session,
            user_id=snapshot.user_id,
            now_utc=now_utc,
            status=claim_result.status,
            reason=getattr(claim_result, "reason", None),
        )

    await answer_channel_bonus_result(callback.message, status=claim_result.status)
    await callback.answer()


@router.callback_query(F.data == "channel_bonus:channel_unavailable")
async def handle_channel_bonus_channel_unavailable(callback: CallbackQuery) -> None:
    await callback.answer(TEXTS_DE["msg.channel.bonus.check.error"], show_alert=True)


@router.callback_query(F.data == "channel_bonus:claimed")
async def handle_channel_bonus_claimed_state(callback: CallbackQuery) -> None:
    await callback.answer()
