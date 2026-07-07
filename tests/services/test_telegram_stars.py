from __future__ import annotations

import traceback
from datetime import timezone

import httpx
import pytest

from app.services.telegram_stars import (
    DEFAULT_TELEGRAM_STARS_TIMEOUT_SECONDS,
    TelegramStarsClient,
    TelegramStarsClientError,
)


class _Response:
    def __init__(self, payload: object, *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self._payload


class _Client:
    def __init__(self, payload: object, *, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.calls: list[dict[str, object]] = []

    async def post(self, url: str, json: dict[str, int]) -> _Response:
        self.calls.append({"url": url, "json": json})
        return _Response(self.payload, status_code=self.status_code)


class _FailingClient:
    async def post(self, url: str, json: dict[str, int]) -> _Response:
        del url, json
        raise httpx.ConnectError("network unavailable")


@pytest.mark.asyncio
async def test_get_star_transactions_parses_incoming_invoice_payment() -> None:
    http_client = _Client(
        {
            "ok": True,
            "result": {
                "transactions": [
                    {
                        "id": "charge-1",
                        "amount": 29,
                        "date": 1_720_000_000,
                        "source": {
                            "type": "user",
                            "transaction_type": "invoice_payment",
                            "user": {"id": 270},
                            "invoice_payload": "invoice-1",
                        },
                    }
                ]
            },
        }
    )
    client = TelegramStarsClient(bot_token="token-secret", http_client=http_client)

    page = await client.get_star_transactions(offset=5, limit=25)

    assert http_client.calls[0]["json"] == {"offset": 5, "limit": 25}
    transaction = page.transactions[0]
    assert transaction.transaction_id == "charge-1"
    assert transaction.amount == 29
    assert transaction.transaction_date.tzinfo == timezone.utc
    assert transaction.is_incoming is True
    assert transaction.source_user_id == 270
    assert transaction.invoice_payload == "invoice-1"
    assert transaction.transaction_type == "invoice_payment"


@pytest.mark.asyncio
async def test_get_star_transactions_preserves_outgoing_refund_shape() -> None:
    http_client = _Client(
        {
            "ok": True,
            "result": {
                "transactions": [
                    {
                        "id": "charge-1",
                        "amount": 29,
                        "date": 1_720_000_000,
                        "receiver": {
                            "type": "user",
                            "transaction_type": "invoice_payment",
                            "user": {"id": 270},
                        },
                    }
                ]
            },
        }
    )
    client = TelegramStarsClient(bot_token="token-secret", http_client=http_client)

    page = await client.get_star_transactions()

    assert page.transactions[0].is_incoming is False
    assert page.transactions[0].source_user_id is None


@pytest.mark.asyncio
async def test_get_star_transactions_sanitizes_transport_errors() -> None:
    client = TelegramStarsClient(bot_token="token-secret", http_client=_FailingClient())

    with pytest.raises(TelegramStarsClientError) as exc_info:
        await client.get_star_transactions()

    assert str(exc_info.value) == "telegram_stars_request_failed"
    assert exc_info.value.error_type == "ConnectError"
    assert "token-secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_star_transactions_sanitizes_http_status_traceback() -> None:
    client = TelegramStarsClient(
        bot_token="token-secret",
        http_client=_Client({"ok": False}, status_code=500),
    )

    with pytest.raises(TelegramStarsClientError) as exc_info:
        await client.get_star_transactions()

    formatted = "".join(
        traceback.format_exception(
            type(exc_info.value),
            exc_info.value,
            exc_info.value.__traceback__,
        )
    )
    assert str(exc_info.value) == "telegram_stars_http_status_error"
    assert exc_info.value.__cause__ is None
    assert "token-secret" not in formatted


@pytest.mark.asyncio
async def test_get_star_transactions_rejects_api_error_without_description_leak() -> None:
    http_client = _Client({"ok": False, "description": "bot token-secret failed"})
    client = TelegramStarsClient(bot_token="token-secret", http_client=http_client)

    with pytest.raises(TelegramStarsClientError) as exc_info:
        await client.get_star_transactions()

    assert str(exc_info.value) == "telegram_stars_api_error"
    assert "token-secret" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_star_transactions_validates_limit() -> None:
    client = TelegramStarsClient(bot_token="token-secret", http_client=_Client({}))

    with pytest.raises(ValueError):
        await client.get_star_transactions(limit=101)


def test_default_timeout_is_short_and_explicit() -> None:
    client = TelegramStarsClient(bot_token="token-secret", http_client=_Client({}))

    assert client.timeout_seconds == DEFAULT_TELEGRAM_STARS_TIMEOUT_SECONDS
