from __future__ import annotations

from datetime import datetime

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.texts.channel_bonus import CHANNEL_BONUS_CHECK_RETRY_TEXT
from app.bot.texts.de import TEXTS_DE
from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.services.channel_bonus import ChannelBonusService

_RESULT_EVENTS = {
    ChannelBonusService.STATUS_CLAIMED: "channel_bonus_claimed",
    ChannelBonusService.STATUS_NOT_SUBSCRIBED: "channel_bonus_check_failed_not_subscribed",
    ChannelBonusService.STATUS_CHECK_RETRY: "channel_bonus_check_retry_required",
    ChannelBonusService.STATUS_CHECK_ERROR: "channel_bonus_check_failed_error",
}

_RESULT_MESSAGES = {
    ChannelBonusService.STATUS_CLAIMED: TEXTS_DE["msg.channel.bonus.success"],
    ChannelBonusService.STATUS_NOT_SUBSCRIBED: TEXTS_DE["msg.channel.bonus.not_subscribed"],
    ChannelBonusService.STATUS_CHECK_RETRY: CHANNEL_BONUS_CHECK_RETRY_TEXT,
    ChannelBonusService.STATUS_CHECK_ERROR: TEXTS_DE["msg.channel.bonus.check.error"],
}


def _result_payload(status: str, reason: str | None) -> dict[str, object]:
    payload: dict[str, object] = {"source": "channel_bonus_check"}
    if status in {
        ChannelBonusService.STATUS_CHECK_RETRY,
        ChannelBonusService.STATUS_CHECK_ERROR,
    }:
        payload["reason"] = reason or "unknown"
    return payload


async def emit_channel_bonus_check_started(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
) -> None:
    await emit_analytics_event(
        session,
        event_type="channel_bonus_check_started",
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload={"source": "channel_bonus_check"},
    )


async def emit_channel_bonus_result_event(
    session: AsyncSession,
    *,
    user_id: int,
    now_utc: datetime,
    status: str,
    reason: str | None,
) -> None:
    event_type = _RESULT_EVENTS.get(status)
    if event_type is None:
        return
    await emit_analytics_event(
        session,
        event_type=event_type,
        source=EVENT_SOURCE_BOT,
        happened_at=now_utc,
        user_id=user_id,
        payload=_result_payload(status, reason),
    )


async def answer_channel_bonus_result(message: Message, *, status: str) -> None:
    text = _RESULT_MESSAGES.get(status)
    if text is not None:
        await message.answer(text)
