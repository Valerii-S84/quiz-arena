from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import payments
from app.economy.purchases.types import PurchaseCreditResult, PurchaseInitResult
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


class _SuccessfulPayment:
    def __init__(self) -> None:
        self.invoice_payload = "inv-1"
        self.telegram_payment_charge_id = "charge-1"

    def model_dump(self, exclude_none: bool = True) -> dict[str, object]:
        assert exclude_none is True
        return {
            "invoice_payload": self.invoice_payload,
            "telegram_payment_charge_id": self.telegram_payment_charge_id,
            "currency": "XTR",
            "total_amount": 29,
        }


class _PaymentMessage(DummyMessage):
    def __init__(self, *, from_user: SimpleNamespace | None) -> None:
        super().__init__()
        self.from_user = from_user
        self.successful_payment = _SuccessfulPayment()


@pytest.mark.asyncio
async def test_handle_buy_with_offer_marks_click_without_conversion(monkeypatch) -> None:
    monkeypatch.setattr(payments, "SessionLocal", DummySessionLocal())
    clicked_calls: list[dict[str, object]] = []
    init_keys: list[str] = []

    async def fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=5)

    async def fake_mark_clicked(session, *, user_id: int, impression_id: int, clicked_at):
        clicked_calls.append({"user_id": user_id, "impression_id": impression_id})
        return True

    async def fake_mark_converted(*args, **kwargs):
        raise AssertionError("conversion must not be recorded before successful payment")

    async def fake_init_purchase(*args, **kwargs):
        init_keys.append(kwargs["idempotency_key"])
        return PurchaseInitResult(
            purchase_id=UUID("123e4567-e89b-12d3-a456-426614174001"),
            invoice_payload="inv-offer-1",
            product_code="ENERGY_10",
            final_stars_amount=10,
            idempotent_replay=False,
        )

    async def fake_mark_invoice_sent(*args, **kwargs):
        return None

    monkeypatch.setattr(payments.UserOnboardingService, "ensure_home_snapshot", fake_home_snapshot)
    monkeypatch.setattr(payments.OfferService, "mark_offer_clicked", fake_mark_clicked)
    monkeypatch.setattr(payments.OfferService, "mark_offer_converted_purchase", fake_mark_converted)
    monkeypatch.setattr(payments.PurchaseService, "init_purchase", fake_init_purchase)
    monkeypatch.setattr(payments.PurchaseService, "mark_invoice_sent", fake_mark_invoice_sent)

    callback = DummyCallback(data="buy:ENERGY_10:offer:42", from_user=SimpleNamespace(id=5))
    await payments.handle_buy(callback)

    assert clicked_calls == [{"user_id": 5, "impression_id": 42}]
    assert len(init_keys) == 1
    assert ":offer:42:" in init_keys[0]


@pytest.mark.asyncio
async def test_handle_successful_payment_marks_offer_conversion(monkeypatch) -> None:
    monkeypatch.setattr(payments, "SessionLocal", DummySessionLocal())
    converted_calls: list[dict[str, object]] = []

    async def fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=77)

    async def fake_apply_payment(*args, **kwargs):
        return PurchaseCreditResult(
            purchase_id=UUID("123e4567-e89b-12d3-a456-426614174099"),
            product_code="ENERGY_10",
            status="CREDITED",
            idempotent_replay=False,
        )

    async def fake_get_by_id(*args, **kwargs):
        return SimpleNamespace(idempotency_key="buy:abcd1234:offer:91:deadbeef10")

    async def fake_mark_converted(session, *, user_id: int, impression_id: int, purchase_id: UUID):
        converted_calls.append(
            {"user_id": user_id, "impression_id": impression_id, "purchase_id": purchase_id}
        )
        return True

    monkeypatch.setattr(payments.UserOnboardingService, "ensure_home_snapshot", fake_home_snapshot)
    monkeypatch.setattr(payments.PurchaseService, "apply_successful_payment", fake_apply_payment)
    monkeypatch.setattr(payments.PurchaseService, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(payments.OfferService, "mark_offer_converted_purchase", fake_mark_converted)

    message = _PaymentMessage(from_user=SimpleNamespace(id=1))
    await payments.handle_successful_payment(message)  # type: ignore[arg-type]

    assert converted_calls == [
        {
            "user_id": 77,
            "impression_id": 91,
            "purchase_id": UUID("123e4567-e89b-12d3-a456-426614174099"),
        }
    ]


@pytest.mark.asyncio
async def test_handle_buy_skips_duel_click_event_without_duel_context(monkeypatch) -> None:
    monkeypatch.setattr(payments, "SessionLocal", DummySessionLocal())

    async def fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=5)

    async def fake_init_purchase(*args, **kwargs):
        return PurchaseInitResult(
            purchase_id=UUID("123e4567-e89b-12d3-a456-426614174010"),
            invoice_payload="inv-premium-1",
            product_code="PREMIUM_WEEK",
            final_stars_amount=29,
            idempotent_replay=False,
        )

    async def fake_mark_invoice_sent(*args, **kwargs):
        return None

    async def unexpected_duel_click(*args, **kwargs):
        raise AssertionError("shop purchase must not emit duel paywall analytics")

    monkeypatch.setattr(payments.UserOnboardingService, "ensure_home_snapshot", fake_home_snapshot)
    monkeypatch.setattr(payments.PurchaseService, "init_purchase", fake_init_purchase)
    monkeypatch.setattr(payments.PurchaseService, "mark_invoice_sent", fake_mark_invoice_sent)
    monkeypatch.setattr(payments, "_emit_duel_paywall_click", unexpected_duel_click)

    callback = DummyCallback(data="buy:PREMIUM_WEEK", from_user=SimpleNamespace(id=5))
    await payments.handle_buy(callback)

    assert callback.bot.sent_invoices[0]["payload"] == "inv-premium-1"


@pytest.mark.asyncio
async def test_handle_buy_emits_duel_click_event_for_duel_context(monkeypatch) -> None:
    monkeypatch.setattr(payments, "SessionLocal", DummySessionLocal())
    duel_clicks: list[dict[str, object]] = []

    async def fake_home_snapshot(session, *, telegram_user):
        return SimpleNamespace(user_id=5)

    async def fake_init_purchase(*args, **kwargs):
        return PurchaseInitResult(
            purchase_id=UUID("123e4567-e89b-12d3-a456-426614174011"),
            invoice_payload="inv-duel-premium-1",
            product_code="PREMIUM_WEEK",
            final_stars_amount=29,
            idempotent_replay=False,
        )

    async def fake_mark_invoice_sent(*args, **kwargs):
        return None

    async def fake_duel_click(session, *, user_id, product_code, happened_at, paywall_context):
        duel_clicks.append(
            {
                "user_id": user_id,
                "product_code": product_code,
                "paywall_context": paywall_context,
            }
        )

    monkeypatch.setattr(payments.UserOnboardingService, "ensure_home_snapshot", fake_home_snapshot)
    monkeypatch.setattr(payments.PurchaseService, "init_purchase", fake_init_purchase)
    monkeypatch.setattr(payments.PurchaseService, "mark_invoice_sent", fake_mark_invoice_sent)
    monkeypatch.setattr(payments, "_emit_duel_paywall_click", fake_duel_click)

    callback = DummyCallback(
        data="buy:PREMIUM_WEEK:duel:close_loss",
        from_user=SimpleNamespace(id=5),
    )
    await payments.handle_buy(callback)

    assert duel_clicks == [
        {
            "user_id": 5,
            "product_code": "PREMIUM_WEEK",
            "paywall_context": "close_loss",
        }
    ]
    assert callback.bot.sent_invoices[0]["payload"] == "inv-duel-premium-1"
