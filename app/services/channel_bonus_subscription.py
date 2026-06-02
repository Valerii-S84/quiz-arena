from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramNetworkError

logger = logging.getLogger(__name__)

REASON_BOT_OR_CHANNEL_CONFIG = "bot_or_channel_config_broken"
REASON_CHANNEL_NOT_CONFIGURED = "channel_not_configured"
REASON_CHECKER_BOT_INVALID_TOKEN = "checker_bot_invalid_token"
REASON_PARTICIPANT_ID_INVALID = "participant_id_invalid"
REASON_TELEGRAM_API_ERROR = "telegram_api_error"
REASON_TELEGRAM_TEMPORARY_ERROR = "telegram_temporary_error"
REASON_USER_NOT_FOUND = "user_not_found"

_SUBSCRIBED_MEMBER_STATUSES = {"creator", "administrator", "member", "restricted"}


@dataclass(frozen=True, slots=True)
class ChannelBonusSubscriptionCheck:
    subscribed: bool | None
    retryable: bool = False
    reason: str | None = None


async def check_bonus_channel_subscription(
    *,
    bot: Bot,
    channel_target: int | str,
    telegram_user_id: int,
    checker_bot_token: str,
) -> ChannelBonusSubscriptionCheck:
    active_bot = bot
    checker_bot: Bot | None = None
    normalized_checker_token = checker_bot_token.strip()
    if normalized_checker_token:
        try:
            checker_bot = Bot(token=normalized_checker_token)
            active_bot = checker_bot
        except ValueError as exc:
            logger.warning("channel_bonus_checker_bot_invalid_token", exc_info=exc)
            return ChannelBonusSubscriptionCheck(
                subscribed=None,
                reason=REASON_CHECKER_BOT_INVALID_TOKEN,
            )

    try:
        member = await active_bot.get_chat_member(chat_id=channel_target, user_id=telegram_user_id)
    except TelegramBadRequest as exc:
        return _handle_bad_request(exc)
    except (TelegramNetworkError, TimeoutError, OSError) as exc:
        logger.warning("channel_bonus_check_temporary_error", exc_info=exc)
        return ChannelBonusSubscriptionCheck(
            subscribed=None,
            retryable=True,
            reason=REASON_TELEGRAM_TEMPORARY_ERROR,
        )
    except TelegramAPIError as exc:
        logger.warning("channel_bonus_check_api_error", exc_info=exc)
        return ChannelBonusSubscriptionCheck(subscribed=None, reason=REASON_TELEGRAM_API_ERROR)
    finally:
        if checker_bot is not None:
            await checker_bot.session.close()

    member_status = str(getattr(member, "status", "")).lower().strip()
    return ChannelBonusSubscriptionCheck(
        subscribed=member_status in _SUBSCRIBED_MEMBER_STATUSES,
    )


def _handle_bad_request(exc: TelegramBadRequest) -> ChannelBonusSubscriptionCheck:
    if "PARTICIPANT_ID_INVALID" in str(exc).upper():
        logger.warning("channel_bonus_participant_id_invalid", exc_info=exc)
        return ChannelBonusSubscriptionCheck(
            subscribed=None,
            retryable=True,
            reason=REASON_PARTICIPANT_ID_INVALID,
        )
    logger.warning("channel_bonus_check_bad_request", exc_info=exc)
    return ChannelBonusSubscriptionCheck(subscribed=None, reason=REASON_BOT_OR_CHANNEL_CONFIG)
