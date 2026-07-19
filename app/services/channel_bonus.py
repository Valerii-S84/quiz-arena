from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.repo.users_repo import UsersRepo
from app.economy.energy.service import EnergyService
from app.services.channel_bonus_subscription import (
    REASON_CHANNEL_NOT_CONFIGURED,
    REASON_USER_NOT_FOUND,
    check_bonus_channel_subscription,
)

logger = logging.getLogger(__name__)

_CHANNEL_BONUS_STATUS_CLAIMED = "CLAIMED"
_CHANNEL_BONUS_STATUS_ALREADY_CLAIMED = "ALREADY_CLAIMED"
_CHANNEL_BONUS_STATUS_NOT_SUBSCRIBED = "NOT_SUBSCRIBED"
_CHANNEL_BONUS_STATUS_CHECK_RETRY = "CHECK_RETRY"
_CHANNEL_BONUS_STATUS_CHECK_ERROR = "CHECK_ERROR"


@dataclass(frozen=True, slots=True)
class ChannelBonusClaimResult:
    status: str
    free_energy: int | None = None
    paid_energy: int | None = None
    reason: str | None = None


def _clean_channel_value(raw_channel_value: str) -> str:
    value = raw_channel_value.strip()
    if value.startswith("http://"):
        value = value.removeprefix("http://")
    elif value.startswith("https://"):
        value = value.removeprefix("https://")

    if value.startswith("t.me/"):
        value = value.removeprefix("t.me/")

    value = value.strip("/")
    if "?" in value:
        value = value.split("?", maxsplit=1)[0]
    if "/" in value:
        value = value.split("/", maxsplit=1)[0]
    return value.strip()


def _resolve_channel_target(raw_channel_value: str) -> int | str | None:
    value = _clean_channel_value(raw_channel_value)
    if not value:
        return None
    if value.lstrip("-").isdigit():
        return int(value)
    if value.startswith("@"):
        username = value[1:].strip()
        if not username:
            return None
        return f"@{username}"
    return f"@{value}"


def _resolve_channel_url(raw_channel_value: str) -> str | None:
    value = raw_channel_value.strip()
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        return value

    cleaned = _clean_channel_value(value)
    if not cleaned or cleaned.lstrip("-").isdigit():
        return None
    if cleaned.startswith("@"):
        cleaned = cleaned[1:]
    if not cleaned:
        return None
    return f"https://t.me/{cleaned}"


async def is_bonus_claimed(session: AsyncSession, *, user_id: int) -> bool:
    user = await UsersRepo.get_by_id(session, user_id)
    if user is None:
        return False
    return user.channel_bonus_claimed_at is not None


async def can_show_prompt(session: AsyncSession, *, user_id: int) -> bool:
    return not await is_bonus_claimed(session, user_id=user_id)


async def should_show_post_game_prompt(
    session: AsyncSession,
    *,
    user_id: int,
    idempotent_replay: bool,
) -> bool:
    if idempotent_replay:
        return False
    if await is_bonus_claimed(session, user_id=user_id):
        return False
    completed_sessions = await QuizSessionsRepo.count_completed_for_user(
        session,
        user_id=user_id,
        cap=2,
    )
    return completed_sessions == 1


async def claim_bonus_if_subscribed(
    session: AsyncSession,
    *,
    user_id: int,
    telegram_user_id: int,
    bot: Bot,
    now_utc: datetime,
) -> ChannelBonusClaimResult:
    settings = get_settings()
    channel_target = _resolve_channel_target(settings.bonus_channel_id)
    if channel_target is None:
        logger.warning("channel_bonus_channel_not_configured")
        return ChannelBonusClaimResult(
            status=_CHANNEL_BONUS_STATUS_CHECK_ERROR,
            reason=REASON_CHANNEL_NOT_CONFIGURED,
        )

    subscription_check = await check_bonus_channel_subscription(
        bot=bot,
        channel_target=channel_target,
        telegram_user_id=telegram_user_id,
        checker_bot_token=str(getattr(settings, "bonus_check_bot_token", "") or ""),
    )
    if subscription_check.subscribed is None:
        status = (
            _CHANNEL_BONUS_STATUS_CHECK_RETRY
            if subscription_check.retryable
            else _CHANNEL_BONUS_STATUS_CHECK_ERROR
        )
        return ChannelBonusClaimResult(status=status, reason=subscription_check.reason)
    if not subscription_check.subscribed:
        return ChannelBonusClaimResult(status=_CHANNEL_BONUS_STATUS_NOT_SUBSCRIBED)

    user = await UsersRepo.get_by_id_for_update(session, user_id)
    if user is None:
        logger.warning("channel_bonus_user_not_found")
        return ChannelBonusClaimResult(
            status=_CHANNEL_BONUS_STATUS_CHECK_ERROR,
            reason=REASON_USER_NOT_FOUND,
        )
    if user.channel_bonus_claimed_at is not None:
        return ChannelBonusClaimResult(status=_CHANNEL_BONUS_STATUS_ALREADY_CLAIMED)

    snapshot = await EnergyService.fill_to_free_cap(session, user_id=user_id, now_utc=now_utc)
    user.channel_bonus_claimed_at = now_utc
    await session.flush()

    return ChannelBonusClaimResult(
        status=_CHANNEL_BONUS_STATUS_CLAIMED,
        free_energy=snapshot.free_energy,
        paid_energy=snapshot.paid_energy,
    )


class ChannelBonusService:
    STATUS_CLAIMED = _CHANNEL_BONUS_STATUS_CLAIMED
    STATUS_ALREADY_CLAIMED = _CHANNEL_BONUS_STATUS_ALREADY_CLAIMED
    STATUS_NOT_SUBSCRIBED = _CHANNEL_BONUS_STATUS_NOT_SUBSCRIBED
    STATUS_CHECK_RETRY = _CHANNEL_BONUS_STATUS_CHECK_RETRY
    STATUS_CHECK_ERROR = _CHANNEL_BONUS_STATUS_CHECK_ERROR

    is_bonus_claimed = staticmethod(is_bonus_claimed)
    can_show_prompt = staticmethod(can_show_prompt)
    should_show_post_game_prompt = staticmethod(should_show_post_game_prompt)
    claim_bonus_if_subscribed = staticmethod(claim_bonus_if_subscribed)

    @staticmethod
    def resolve_channel_url() -> str | None:
        return _resolve_channel_url(get_settings().bonus_channel_id)
