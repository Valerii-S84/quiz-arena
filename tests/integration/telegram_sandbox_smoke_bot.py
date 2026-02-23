from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.methods import (
    AnswerCallbackQuery,
    AnswerPreCheckoutQuery,
    GetMe,
    SendInvoice,
    SendMessage,
)
from aiogram.types import Message as TelegramMessage
from aiogram.types import User as TelegramUser

from app.api.routes import telegram_webhook
from app.workers.tasks import telegram_updates
from tests.integration.telegram_sandbox_smoke_fixtures import (
    UTC,
    WEBHOOK_SECRET,
    _private_chat_payload,
)


class _InProcessUpdateQueue:
    def __init__(self) -> None:
        self._tasks: list[asyncio.Task[str]] = []

    def delay(self, *, update_payload: dict[str, object], update_id: int) -> None:
        self._tasks.append(
            asyncio.create_task(
                telegram_updates.process_update_async(update_payload, update_id=update_id)
            )
        )

    async def drain(self) -> None:
        if not self._tasks:
            return
        tasks = self._tasks
        self._tasks = []
        await asyncio.gather(*tasks)


class _BotApiStub:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, object]] = []
        self.sent_invoices: list[dict[str, object]] = []
        self.callback_answers: list[dict[str, object]] = []
        self.precheckout_answers: list[dict[str, object]] = []
        self._message_seq = 1_000

    def _next_message_id(self) -> int:
        self._message_seq += 1
        return self._message_seq

    def _build_message(self, *, chat_id: int, text: str | None = None) -> TelegramMessage:
        payload: dict[str, object] = {
            "message_id": self._next_message_id(),
            "date": int(datetime.now(UTC).timestamp()),
            "chat": _private_chat_payload(chat_id),
        }
        if text is not None:
            payload["text"] = text
        return TelegramMessage.model_validate(payload)

    async def dispatch(self, method: object) -> object:
        if isinstance(method, GetMe):
            return TelegramUser(
                id=777_000_001,
                is_bot=True,
                first_name="QuizArena",
                username="quiz_arena_smoke_bot",
            )

        if isinstance(method, SendMessage):
            chat_id = int(method.chat_id)
            self.sent_messages.append(
                {
                    "chat_id": chat_id,
                    "text": method.text,
                    "reply_markup": method.reply_markup,
                }
            )
            return self._build_message(chat_id=chat_id, text=method.text)

        if isinstance(method, SendInvoice):
            total_amount = method.prices[0].amount if method.prices else 0
            chat_id = int(method.chat_id)
            self.sent_invoices.append(
                {
                    "chat_id": chat_id,
                    "invoice_payload": method.payload,
                    "total_amount": total_amount,
                }
            )
            return self._build_message(chat_id=chat_id)

        if isinstance(method, AnswerCallbackQuery):
            self.callback_answers.append(
                {
                    "callback_query_id": method.callback_query_id,
                    "text": method.text,
                    "show_alert": method.show_alert,
                }
            )
            return True

        if isinstance(method, AnswerPreCheckoutQuery):
            self.precheckout_answers.append(
                {
                    "pre_checkout_query_id": method.pre_checkout_query_id,
                    "ok": method.ok,
                    "error_message": method.error_message,
                }
            )
            return True

        raise AssertionError(f"Unexpected Telegram API method call: {type(method)!r}")


def _configure_webhook_processing(
    monkeypatch: pytest.MonkeyPatch, bot_api: _BotApiStub
) -> _InProcessUpdateQueue:
    queue = _InProcessUpdateQueue()
    monkeypatch.setattr(
        telegram_webhook,
        "get_settings",
        lambda: SimpleNamespace(telegram_webhook_secret=WEBHOOK_SECRET),
    )
    monkeypatch.setattr(telegram_webhook, "process_telegram_update", queue)
    monkeypatch.setattr(
        telegram_updates,
        "build_bot",
        lambda: Bot(token="42:TEST", default=DefaultBotProperties()),
    )

    async def fake_bot_call(
        self: Bot, method: object, request_timeout: int | None = None
    ) -> object:
        _ = request_timeout
        return await bot_api.dispatch(method)

    monkeypatch.setattr(Bot, "__call__", fake_bot_call)
    return queue
