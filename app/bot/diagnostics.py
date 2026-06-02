from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass
from typing import Any

import structlog
from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery, ForceReply, Message, Update

from app.bot.diagnostic_sanitizers import payload_metadata, scalar_metadata
from app.bot.texts.de import TEXTS_DE
from app.core.config import get_settings

logger = structlog.get_logger(__name__)
_original_send_message = Bot.send_message
_send_message_trace_installed = False


def _trace_enabled() -> bool:
    return bool(getattr(get_settings(), "telegram_debug_trace_enabled", False))


async def _traced_send_message(
    self: Bot,
    chat_id: Any,
    text: str,
    *args: Any,
    **kwargs: Any,
) -> Message:
    reply_markup = kwargs.get("reply_markup")
    is_force_reply = isinstance(reply_markup, ForceReply)
    if _trace_enabled() and (("Promo-Code" in text) or is_force_reply):
        logging.warning(
            "PROMO_OUTGOING chat_id=%s text=%r markup=%s\nSTACK:\n%s",
            chat_id,
            payload_metadata(text),
            type(reply_markup).__name__ if reply_markup else None,
            "".join(traceback.format_stack(limit=25)),
        )
    return await _original_send_message(self, chat_id, text, *args, **kwargs)


def install_outgoing_trace() -> None:
    global _send_message_trace_installed
    if _send_message_trace_installed:
        return
    Bot.send_message = _traced_send_message  # type: ignore[method-assign]
    _send_message_trace_installed = True


@dataclass(frozen=True, slots=True)
class TelegramUpdateTrace:
    update_type: str
    user_id: int | None
    chat_id: int | None
    message_text: str | None
    callback_data: str | None
    reply_to_message_id: int | None
    reply_to_text: str | None
    reply_to_is_bot: bool | None
    reply_to_is_promo_prompt: bool


def _message_trace(message: Message) -> TelegramUpdateTrace:
    reply_to = message.reply_to_message
    reply_to_text = reply_to.text if reply_to is not None else None
    reply_to_user = reply_to.from_user if reply_to is not None else None
    return TelegramUpdateTrace(
        update_type="message",
        user_id=message.from_user.id if message.from_user else None,
        chat_id=message.chat.id if message.chat else None,
        message_text=message.text,
        callback_data=None,
        reply_to_message_id=reply_to.message_id if reply_to is not None else None,
        reply_to_text=reply_to_text,
        reply_to_is_bot=reply_to_user.is_bot if reply_to_user is not None else None,
        reply_to_is_promo_prompt=bool(
            reply_to_text and reply_to_text.startswith(TEXTS_DE["msg.promo.reply_prefix"])
        ),
    )


def _callback_trace(callback: CallbackQuery) -> TelegramUpdateTrace:
    chat_id = callback.message.chat.id if isinstance(callback.message, Message) else None
    return TelegramUpdateTrace(
        update_type="callback_query",
        user_id=callback.from_user.id if callback.from_user else None,
        chat_id=chat_id,
        message_text=None,
        callback_data=callback.data,
        reply_to_message_id=None,
        reply_to_text=None,
        reply_to_is_bot=None,
        reply_to_is_promo_prompt=False,
    )


def build_update_trace(update: Update) -> TelegramUpdateTrace | None:
    if update.message is not None:
        return _message_trace(update.message)
    if update.callback_query is not None:
        return _callback_trace(update.callback_query)
    return None


async def _state_snapshot(
    *,
    dispatcher: Dispatcher,
    bot: Bot,
    trace: TelegramUpdateTrace,
) -> tuple[str | None, dict[str, object]]:
    if trace.chat_id is None or trace.user_id is None:
        return None, {}
    context = dispatcher.fsm.get_context(
        bot=bot,
        chat_id=trace.chat_id,
        user_id=trace.user_id,
    )
    data = await context.get_data()
    safe_data: dict[str, object] = {}
    for key, value in data.items():
        if isinstance(value, (str, int, float, bool, type(None))):
            safe_data[key] = scalar_metadata(value)
    return await context.get_state(), safe_data


async def log_update_trace(
    *,
    phase: str,
    update_id: int,
    update: Update,
    dispatcher: Dispatcher,
    bot: Bot,
) -> None:
    if not _trace_enabled():
        return
    trace = build_update_trace(update)
    if trace is None:
        logger.warning(
            "telegram_update_trace",
            phase=phase,
            update_id=update_id,
            update_type="other",
        )
        return

    state, data = await _state_snapshot(dispatcher=dispatcher, bot=bot, trace=trace)
    logger.warning(
        "telegram_update_trace",
        phase=phase,
        update_id=update_id,
        update_type=trace.update_type,
        user_id=trace.user_id,
        chat_id=trace.chat_id,
        message_text_metadata=payload_metadata(trace.message_text),
        callback_data_metadata=payload_metadata(trace.callback_data),
        state=state,
        fsm_data=data,
        reply_to_message_id=trace.reply_to_message_id,
        reply_to_text_metadata=payload_metadata(trace.reply_to_text),
        reply_to_is_bot=trace.reply_to_is_bot,
        reply_to_is_promo_prompt=trace.reply_to_is_promo_prompt,
    )
