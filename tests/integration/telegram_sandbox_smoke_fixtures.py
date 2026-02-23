from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

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
from httpx import AsyncClient

from app.api.routes import telegram_webhook
from app.core.config import get_settings
from app.db.models.promo_codes import PromoCode
from app.db.models.users import User
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.services.promo_codes import hash_promo_code, normalize_promo_code
from app.workers.tasks import telegram_updates

UTC = timezone.utc
WEBHOOK_SECRET = "smoke-secret"


def _telegram_user_payload(telegram_user_id: int) -> dict[str, object]:
    return {
        "id": telegram_user_id,
        "is_bot": False,
        "first_name": "Smoke",
        "username": None,
        "language_code": "de",
    }


def _private_chat_payload(telegram_user_id: int) -> dict[str, object]:
    return {
        "id": telegram_user_id,
        "type": "private",
        "first_name": "Smoke",
        "username": None,
    }


def _message_update(
    *,
    update_id: int,
    telegram_user_id: int,
    message_id: int,
    text: str | None = None,
    successful_payment: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "update_id": update_id,
        "message": {
            "message_id": message_id,
            "date": int(datetime.now(UTC).timestamp()),
            "chat": _private_chat_payload(telegram_user_id),
            "from": _telegram_user_payload(telegram_user_id),
        },
    }
    message_payload = payload["message"]
    if isinstance(message_payload, dict):
        if text is not None:
            message_payload["text"] = text
            if text.startswith("/promo "):
                message_payload["entities"] = [{"offset": 0, "length": 6, "type": "bot_command"}]
        if successful_payment is not None:
            message_payload["successful_payment"] = successful_payment
    return payload


def _callback_update(
    *,
    update_id: int,
    telegram_user_id: int,
    callback_query_id: str,
    data: str,
) -> dict[str, object]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": callback_query_id,
            "from": _telegram_user_payload(telegram_user_id),
            "chat_instance": f"chat-instance-{telegram_user_id}",
            "data": data,
            "message": {
                "message_id": 10_000 + update_id,
                "date": int(datetime.now(UTC).timestamp()),
                "chat": _private_chat_payload(telegram_user_id),
                "text": "callback source",
            },
        },
    }


def _precheckout_update(
    *,
    update_id: int,
    telegram_user_id: int,
    precheckout_id: str,
    invoice_payload: str,
    total_amount: int,
) -> dict[str, object]:
    return {
        "update_id": update_id,
        "pre_checkout_query": {
            "id": precheckout_id,
            "from": _telegram_user_payload(telegram_user_id),
            "currency": "XTR",
            "total_amount": total_amount,
            "invoice_payload": invoice_payload,
        },
    }


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


async def _post_webhook_update(client: AsyncClient, update_payload: dict[str, object]) -> None:
    response = await client.post(
        "/webhook/telegram",
        json=update_payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "queued"}


async def _create_user(*, telegram_user_id: int, first_name: str) -> User:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=telegram_user_id,
            referral_code=f"R{uuid4().hex[:10].upper()}",
            username=None,
            first_name=first_name,
            referred_by_user_id=None,
        )
        return user


async def _create_discount_promo_code(
    *,
    raw_code: str,
    discount_percent: int,
    target_scope: str,
    now_utc: datetime,
) -> PromoCode:
    normalized = normalize_promo_code(raw_code)
    code_hash = hash_promo_code(
        normalized_code=normalized,
        pepper=get_settings().promo_secret_pepper,
    )
    promo_code = PromoCode(
        id=abs(hash((raw_code, target_scope))) % 1_000_000_000 + 1,
        code_hash=code_hash,
        code_prefix=normalized[:8] or "PROMO",
        campaign_name="telegram-smoke",
        promo_type="PERCENT_DISCOUNT",
        grant_premium_days=None,
        discount_percent=discount_percent,
        target_scope=target_scope,
        status="ACTIVE",
        valid_from=now_utc - timedelta(days=1),
        valid_until=now_utc + timedelta(days=1),
        max_total_uses=50,
        used_total=0,
        max_uses_per_user=1,
        new_users_only=False,
        first_purchase_only=False,
        created_by="integration-test",
        created_at=now_utc,
        updated_at=now_utc,
    )
    async with SessionLocal.begin() as session:
        session.add(promo_code)
        await session.flush()
    return promo_code


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
