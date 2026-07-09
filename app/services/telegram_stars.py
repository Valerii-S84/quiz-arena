from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

DEFAULT_TELEGRAM_API_BASE_URL = "https://api.telegram.org"
DEFAULT_TELEGRAM_STARS_TIMEOUT_SECONDS = 5.0


class TelegramStarsClientError(RuntimeError):
    def __init__(self, message: str, *, error_type: str | None = None) -> None:
        super().__init__(message)
        self.error_type = error_type


@dataclass(frozen=True)
class TelegramStarTransaction:
    transaction_id: str
    amount: int
    transaction_date: datetime
    source: dict[str, object] | None
    receiver: dict[str, object] | None
    raw_payload: dict[str, object]

    @property
    def is_incoming(self) -> bool:
        return self.source is not None and self.receiver is None

    @property
    def source_user_id(self) -> int | None:
        return _partner_user_id(self.source)

    @property
    def receiver_user_id(self) -> int | None:
        return _partner_user_id(self.receiver)

    @property
    def partner_user_id(self) -> int | None:
        return self.source_user_id if self.source is not None else self.receiver_user_id

    @property
    def invoice_payload(self) -> str | None:
        payload = _partner_invoice_payload(self.source)
        if payload is not None:
            return payload
        if self.source is None and self.transaction_type == "invoice_payment":
            return _partner_invoice_payload(self.receiver)
        return None

    @property
    def transaction_type(self) -> str | None:
        partner = self.source if self.source is not None else self.receiver
        if partner is None:
            return None
        value = partner.get("transaction_type")
        return value if isinstance(value, str) else None


def _partner_invoice_payload(partner: dict[str, object] | None) -> str | None:
    if partner is None:
        return None
    payload = partner.get("invoice_payload")
    return payload if isinstance(payload, str) else None


def _partner_user_id(partner: dict[str, object] | None) -> int | None:
    if partner is None:
        return None
    user = partner.get("user")
    if not isinstance(user, dict):
        return None
    user_id = user.get("id")
    return user_id if isinstance(user_id, int) else None


@dataclass(frozen=True)
class TelegramStarTransactionsPage:
    transactions: list[TelegramStarTransaction]


class TelegramStarsClient:
    def __init__(
        self,
        *,
        bot_token: str,
        base_url: str = DEFAULT_TELEGRAM_API_BASE_URL,
        timeout_seconds: float = DEFAULT_TELEGRAM_STARS_TIMEOUT_SECONDS,
        http_client: Any | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._http_client = http_client

    async def get_star_transactions(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> TelegramStarTransactionsPage:
        _validate_pagination(offset=offset, limit=limit)
        payload = {"offset": offset, "limit": limit}
        response_payload = await self._post_telegram_method("getStarTransactions", payload)
        return _parse_star_transactions_page(response_payload)

    async def _post_telegram_method(
        self,
        method_name: str,
        payload: dict[str, int],
    ) -> dict[str, object]:
        client = self._http_client
        close_client = client is None
        if client is None:
            client = httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.post(self._method_url(method_name), json=payload)
        except httpx.HTTPError as exc:
            raise TelegramStarsClientError(
                "telegram_stars_request_failed",
                error_type=type(exc).__name__,
            ) from None
        finally:
            if close_client:
                await client.aclose()
        _raise_for_status_without_url(response)
        return _parse_api_response(response)

    def _method_url(self, method_name: str) -> str:
        return f"{self._base_url}/bot{self._bot_token}/{method_name}"


def _validate_pagination(*, offset: int, limit: int) -> None:
    if offset < 0:
        raise ValueError("offset must be non-negative")
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")


def _raise_for_status_without_url(response: httpx.Response) -> None:
    status_code = getattr(response, "status_code", 200)
    if status_code >= 400:
        raise TelegramStarsClientError(
            "telegram_stars_http_status_error",
            error_type=f"HTTPStatus{status_code}",
        )


def _parse_api_response(response: httpx.Response) -> dict[str, object]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise TelegramStarsClientError("telegram_stars_invalid_json") from exc
    if not isinstance(payload, dict):
        raise TelegramStarsClientError("telegram_stars_invalid_response")
    ok = payload.get("ok")
    result = payload.get("result")
    if ok is not True or not isinstance(result, dict):
        raise TelegramStarsClientError("telegram_stars_api_error")
    return result


def _parse_star_transactions_page(payload: dict[str, object]) -> TelegramStarTransactionsPage:
    transactions_raw = payload.get("transactions")
    if not isinstance(transactions_raw, list):
        raise TelegramStarsClientError("telegram_stars_invalid_transactions")
    return TelegramStarTransactionsPage(
        transactions=[_parse_star_transaction(item) for item in transactions_raw]
    )


def _parse_star_transaction(payload: object) -> TelegramStarTransaction:
    if not isinstance(payload, dict):
        raise TelegramStarsClientError("telegram_stars_invalid_transaction")
    transaction_id = payload.get("id")
    amount = payload.get("amount")
    transaction_date = payload.get("date")
    if not isinstance(transaction_id, str) or not isinstance(amount, int):
        raise TelegramStarsClientError("telegram_stars_invalid_transaction")
    if not isinstance(transaction_date, int):
        raise TelegramStarsClientError("telegram_stars_invalid_transaction")
    source = _optional_mapping(payload.get("source"))
    receiver = _optional_mapping(payload.get("receiver"))
    return TelegramStarTransaction(
        transaction_id=transaction_id,
        amount=amount,
        transaction_date=datetime.fromtimestamp(transaction_date, tz=timezone.utc),
        source=source,
        receiver=receiver,
        raw_payload=dict(payload),
    )


def _optional_mapping(value: object) -> dict[str, object] | None:
    return dict(value) if isinstance(value, dict) else None
