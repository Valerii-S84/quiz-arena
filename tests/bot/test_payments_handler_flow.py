from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import payments
from app.bot.texts.de import TEXTS_DE
from app.economy.purchases.errors import PurchaseInitValidationError, PurchasePrecheckoutValidationError
from app.economy.purchases.types import PurchaseCreditResult, PurchaseInitResult
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


class _PreCheckoutQuery:
    def __init__(self, *, from_user: SimpleNamespace, invoice_payload: str, total_amount: int) -> None:
        self.from_user = from_user
        self.invoice_payload = invoice_payload
        self.total_amount = total_amount
        self.calls: list[dict[str, object]] = []

    async def answer(self, *, ok: bool, error_message: str | None = None) -> None:
        self.calls.append({"ok": ok, "error_message": error_message})


class _SuccessfulPayment:
    def __init__(self) -> None:
        self.invoice_payload = "inv-1"
        self.telegram_payment_charge_id = "charge-1"

    def model_dump(self, exclude_none: bool = True) -> dict[str, object]:
        return {
            "invoice_payload": self.invoice_payload,
            "telegram_payment_charge_id": self.telegram_payment_charge_id,
        }


class _PaymentMessage(DummyMessage):
    def __init__(self, *, from_user: SimpleNamespace | None, successful_payment: _SuccessfulPayment | None) -> None:
        super().__init__()
        self.from_user = from_user
        self.successful_payment = successful_payment


@pytest.mark.asyncio
async def test_handle_buy_rejects_invalid_payload() -> None:
    callback = DummyCallback(data="buy:bad:payload", from_user=SimpleNamespace(id=1))

    await payments.handle_buy(callback)

    assert callback.answer_calls[0]["show_alert"] is True


@pytest.mark.asyncio
async def test_handle_buy_handles_init_purchase_failure(monkeypatch) -> None:
    monkeypatch.setattr(payments, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=5)

    async def _fake_init_purchase(*args, **kwargs):
        raise PurchaseInitValidationError()

    monkeypatch.setattr(payments.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(payments.PurchaseService, "init_purchase", _fake_init_purchase)

    callback = DummyCallback(data="buy:ENERGY_10", from_user=SimpleNamespace(id=1))
    await payments.handle_buy(callback)

    assert callback.answer_calls[0]["text"] == TEXTS_DE["msg.purchase.error.failed"]


@pytest.mark.asyncio
async def test_handle_buy_handles_send_invoice_failure(monkeypatch) -> None:
    monkeypatch.setattr(payments, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=5)

    async def _fake_init_purchase(*args, **kwargs):
        return PurchaseInitResult(
            purchase_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            invoice_payload="inv-1",
            product_code="ENERGY_10",
            final_stars_amount=10,
            idempotent_replay=False,
        )

    monkeypatch.setattr(payments.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(payments.PurchaseService, "init_purchase", _fake_init_purchase)

    callback = DummyCallback(data="buy:ENERGY_10", from_user=SimpleNamespace(id=1))
    callback.bot.raise_on_send_invoice = True
    await payments.handle_buy(callback)

    assert callback.answer_calls[0]["text"] == TEXTS_DE["msg.purchase.error.failed"]


@pytest.mark.asyncio
async def test_handle_precheckout_rejects_invalid_payload(monkeypatch) -> None:
    monkeypatch.setattr(payments, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=9)

    async def _fake_validate(*args, **kwargs):
        raise PurchasePrecheckoutValidationError()

    monkeypatch.setattr(payments.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(payments.PurchaseService, "validate_precheckout", _fake_validate)

    query = _PreCheckoutQuery(from_user=SimpleNamespace(id=3), invoice_payload="inv-1", total_amount=10)
    await payments.handle_precheckout(query)  # type: ignore[arg-type]

    assert query.calls == [{"ok": False, "error_message": TEXTS_DE["msg.purchase.error.failed"]}]


@pytest.mark.asyncio
async def test_handle_successful_payment_sends_success_text(monkeypatch) -> None:
    monkeypatch.setattr(payments, "SessionLocal", DummySessionLocal())

    async def _fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=77)

    async def _fake_apply_payment(*args, **kwargs):
        return PurchaseCreditResult(
            purchase_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            product_code="PREMIUM_MONTH",
            status="CREDITED",
            idempotent_replay=False,
        )

    monkeypatch.setattr(payments.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(payments.PurchaseService, "apply_successful_payment", _fake_apply_payment)

    message = _PaymentMessage(from_user=SimpleNamespace(id=1), successful_payment=_SuccessfulPayment())
    await payments.handle_successful_payment(message)  # type: ignore[arg-type]

    assert message.answers[0].text == TEXTS_DE["msg.purchase.success.premium"]
