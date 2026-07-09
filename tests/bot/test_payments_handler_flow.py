from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from aiogram.types import RefundedPayment

from app.bot.handlers import payments, payments_runtime
from app.bot.texts.de import TEXTS_DE
from app.economy.purchases.errors import (
    PurchaseInitValidationError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
    PurchaseRefundValidationError,
)
from app.economy.purchases.types import PurchaseCreditResult, PurchaseInitResult
from tests.bot.helpers import DummyCallback, DummyMessage, DummySessionLocal


class _PreCheckoutQuery:
    def __init__(
        self, *, from_user: SimpleNamespace, invoice_payload: str, total_amount: int, query_id: str
    ) -> None:
        self.id = query_id
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
        self.currency = "XTR"
        self.total_amount = 29

    def model_dump(self, exclude_none: bool = True) -> dict[str, object]:
        assert exclude_none is True
        return {
            "invoice_payload": self.invoice_payload,
            "telegram_payment_charge_id": self.telegram_payment_charge_id,
            "currency": "XTR",
            "total_amount": 29,
        }


def _refunded_payment(
    *,
    invoice_payload: str = "inv-1",
    currency: str = "XTR",
    total_amount: int = 29,
) -> RefundedPayment:
    return RefundedPayment.model_construct(
        currency=currency,
        total_amount=total_amount,
        invoice_payload=invoice_payload,
        telegram_payment_charge_id="charge-1",
    )


class _PaymentMessage(DummyMessage):
    def __init__(
        self,
        *,
        from_user: SimpleNamespace | None,
        successful_payment: _SuccessfulPayment | None,
    ) -> None:
        super().__init__()
        self.from_user = from_user
        self.successful_payment = successful_payment


class _RefundedPaymentMessage(DummyMessage):
    def __init__(
        self,
        *,
        from_user: SimpleNamespace | None,
        refunded_payment: RefundedPayment | None,
    ) -> None:
        super().__init__()
        self.from_user = from_user
        self.refunded_payment = refunded_payment


class _Logger:
    def __init__(self) -> None:
        self.infos: list[tuple[str, dict[str, object]]] = []
        self.warnings: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **payload: object) -> None:
        self.infos.append((event, payload))

    def warning(self, event: str, **payload: object) -> None:
        self.warnings.append((event, payload))


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
async def test_handle_buy_rejects_unknown_product(monkeypatch) -> None:
    monkeypatch.setattr(payments, "SessionLocal", DummySessionLocal())

    async def _fake_init_purchase(*args, **kwargs):
        raise AssertionError("init_purchase must not be called for disabled products")

    monkeypatch.setattr(payments.PurchaseService, "init_purchase", _fake_init_purchase)

    callback = DummyCallback(data="buy:UNKNOWN_PRODUCT", from_user=SimpleNamespace(id=1))
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

    query = _PreCheckoutQuery(
        from_user=SimpleNamespace(id=3),
        invoice_payload="inv-1",
        total_amount=10,
        query_id="pre-1",
    )
    await payments.handle_precheckout(query)  # type: ignore[arg-type]

    assert query.calls == [{"ok": False, "error_message": TEXTS_DE["msg.purchase.error.failed"]}]


@pytest.mark.asyncio
async def test_handle_precheckout_passes_query_id_to_runtime(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    async def _fake_validate_precheckout(
        *,
        telegram_user,
        invoice_payload,
        total_amount,
        precheckout_query_id,
    ):
        calls.append(
            {
                "telegram_user_id": telegram_user.id,
                "invoice_payload": invoice_payload,
                "total_amount": total_amount,
                "precheckout_query_id": precheckout_query_id,
            }
        )

    monkeypatch.setattr(payments, "validate_precheckout", _fake_validate_precheckout)

    query = _PreCheckoutQuery(
        from_user=SimpleNamespace(id=3),
        invoice_payload="inv-2",
        total_amount=29,
        query_id="pre-2",
    )
    await payments.handle_precheckout(query)  # type: ignore[arg-type]

    assert calls == [
        {
            "telegram_user_id": 3,
            "invoice_payload": "inv-2",
            "total_amount": 29,
            "precheckout_query_id": "pre-2",
        }
    ]
    assert query.calls == [{"ok": True, "error_message": None}]


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

    async def _fake_get_by_id(*args, **kwargs):
        return None

    monkeypatch.setattr(payments.UserOnboardingService, "ensure_home_snapshot", _fake_home_snapshot)
    monkeypatch.setattr(payments.PurchaseService, "apply_successful_payment", _fake_apply_payment)
    monkeypatch.setattr(payments.PurchaseService, "get_by_id", _fake_get_by_id)

    message = _PaymentMessage(
        from_user=SimpleNamespace(id=1), successful_payment=_SuccessfulPayment()
    )
    await payments.handle_successful_payment(message)  # type: ignore[arg-type]

    assert message.answers[0].text == TEXTS_DE["msg.purchase.success.premium"]


@pytest.mark.asyncio
async def test_handle_successful_payment_logs_received_update_without_raw_payload(
    monkeypatch,
) -> None:
    logger = _Logger()
    monkeypatch.setattr(payments, "logger", logger)

    async def _fake_apply_payment(*args, **kwargs):
        return PurchaseCreditResult(
            purchase_id=UUID("123e4567-e89b-12d3-a456-426614174000"),
            product_code="PREMIUM_WEEK",
            status="CREDITED",
            idempotent_replay=False,
        )

    monkeypatch.setattr(payments, "apply_successful_payment", _fake_apply_payment)

    payment = _SuccessfulPayment()
    payment.invoice_payload = "invoice-raw-value"
    message = _PaymentMessage(from_user=SimpleNamespace(id=1), successful_payment=payment)

    await payments.handle_successful_payment(message)  # type: ignore[arg-type]

    assert logger.infos[0][0] == "payment_successful_update_received"
    assert logger.infos[0][1]["invoice_payload_hash"] != payment.invoice_payload
    assert (
        logger.infos[0][1]["telegram_payment_charge_id_hash"] != payment.telegram_payment_charge_id
    )
    assert "invoice_payload" not in logger.infos[0][1]
    assert "telegram_payment_charge_id" not in logger.infos[0][1]
    assert payment.invoice_payload not in str(logger.infos)
    assert payment.telegram_payment_charge_id not in str(logger.infos)
    assert "token" not in str(logger.infos).lower()


@pytest.mark.asyncio
async def test_handle_successful_payment_sends_failure_text_for_validation_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(payments, "SessionLocal", DummySessionLocal())

    async def _fake_apply_payment(*args, **kwargs):
        raise PurchasePrecheckoutValidationError()

    logger = _Logger()
    monkeypatch.setattr(payments, "logger", logger)
    monkeypatch.setattr(payments, "apply_successful_payment", _fake_apply_payment)

    payment = _SuccessfulPayment()
    message = _PaymentMessage(from_user=SimpleNamespace(id=1), successful_payment=payment)
    await payments.handle_successful_payment(message)  # type: ignore[arg-type]

    assert message.answers[0].text == TEXTS_DE["msg.purchase.error.failed"]
    assert logger.warnings[0][0] == "payment_credit_failed"
    assert (
        logger.warnings[0][1]["telegram_payment_charge_id_hash"]
        != payment.telegram_payment_charge_id
    )
    assert "telegram_payment_charge_id" not in logger.warnings[0][1]
    assert payment.telegram_payment_charge_id not in str(logger.warnings)


@pytest.mark.asyncio
async def test_handle_refunded_payment_applies_refund_update(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    async def _fake_refund_payment_update(*, telegram_user, refunded_payment, now_utc):
        calls.append(
            {
                "telegram_user_id": telegram_user.id,
                "refunded_payment": refunded_payment,
                "now_utc": now_utc,
            }
        )

    monkeypatch.setattr(payments, "refund_payment_update", _fake_refund_payment_update)

    refund = _refunded_payment()
    message = _RefundedPaymentMessage(from_user=SimpleNamespace(id=1), refunded_payment=refund)
    await payments.handle_refunded_payment(message)  # type: ignore[arg-type]

    assert calls[0]["telegram_user_id"] == 1
    assert calls[0]["refunded_payment"] is refund
    assert message.answers == []


@pytest.mark.asyncio
async def test_handle_refunded_payment_logs_received_update_without_raw_payload(
    monkeypatch,
) -> None:
    logger = _Logger()
    monkeypatch.setattr(payments, "logger", logger)

    async def _fake_refund_payment_update(*args, **kwargs):
        return None

    monkeypatch.setattr(payments, "refund_payment_update", _fake_refund_payment_update)

    refund = _refunded_payment(invoice_payload="invoice-raw-value")
    message = _RefundedPaymentMessage(from_user=SimpleNamespace(id=1), refunded_payment=refund)

    await payments.handle_refunded_payment(message)  # type: ignore[arg-type]

    assert logger.infos[0][0] == "payment_refunded_update_received"
    assert logger.infos[0][1]["invoice_payload_hash"] != refund.invoice_payload
    assert (
        logger.infos[0][1]["telegram_payment_charge_id_hash"] != refund.telegram_payment_charge_id
    )
    assert "invoice_payload" not in logger.infos[0][1]
    assert "telegram_payment_charge_id" not in logger.infos[0][1]
    assert refund.invoice_payload not in str(logger.infos)
    assert refund.telegram_payment_charge_id not in str(logger.infos)
    assert "token" not in str(logger.infos).lower()


@pytest.mark.asyncio
async def test_handle_refunded_payment_reraises_missing_purchase_for_worker_retry(
    monkeypatch,
) -> None:
    async def _fake_refund_payment_update(*args, **kwargs):
        raise PurchaseNotFoundError()

    logger = _Logger()
    monkeypatch.setattr(payments, "logger", logger)
    monkeypatch.setattr(payments, "refund_payment_update", _fake_refund_payment_update)

    refund = _refunded_payment()
    message = _RefundedPaymentMessage(from_user=SimpleNamespace(id=1), refunded_payment=refund)

    with pytest.raises(PurchaseNotFoundError):
        await payments.handle_refunded_payment(message)  # type: ignore[arg-type]

    assert message.answers == []
    assert logger.warnings[0][0] == "payment_refund_update_failed"
    assert (
        logger.warnings[0][1]["telegram_payment_charge_id_hash"]
        != refund.telegram_payment_charge_id
    )
    assert "telegram_payment_charge_id" not in logger.warnings[0][1]
    assert refund.telegram_payment_charge_id not in str(logger.warnings)


@pytest.mark.asyncio
async def test_refund_payment_update_uses_charge_lookup_and_refund_service(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    purchase_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    refund = _refunded_payment()
    purchase = SimpleNamespace(
        id=purchase_id,
        user_id=77,
        invoice_payload=refund.invoice_payload,
        telegram_payment_charge_id=None,
        status="PAID_UNCREDITED",
        paid_at=now_utc,
        currency="XTR",
        stars_amount=29,
    )
    calls: list[dict[str, object]] = []

    async def _fake_home_snapshot(session, *, telegram_user):
        del session
        assert telegram_user.id == 270
        return SimpleNamespace(user_id=77)

    async def _fake_get_by_charge_id(_session, telegram_payment_charge_id: str):
        assert telegram_payment_charge_id == refund.telegram_payment_charge_id
        return purchase

    async def _fake_refund_purchase(
        _session,
        *,
        purchase_id: UUID,
        now_utc: datetime,
        provider_refund_confirmed: bool,
    ):
        calls.append(
            {
                "purchase_id": purchase_id,
                "now_utc": now_utc,
                "provider_refund_confirmed": provider_refund_confirmed,
            }
        )
        return SimpleNamespace(status="REFUNDED")

    monkeypatch.setattr(payments_runtime, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(
        payments_runtime.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_home_snapshot,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_telegram_payment_charge_id_for_update",
        _fake_get_by_charge_id,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    result = await payments_runtime.refund_payment_update(
        telegram_user=SimpleNamespace(id=270),  # type: ignore[arg-type]
        refunded_payment=refund,  # type: ignore[arg-type]
        now_utc=now_utc,
    )

    assert result.status == "REFUNDED"
    assert calls == [
        {
            "purchase_id": purchase_id,
            "now_utc": now_utc,
            "provider_refund_confirmed": True,
        }
    ]


@pytest.mark.asyncio
async def test_refund_payment_update_falls_back_to_invoice_payload_before_refund(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    purchase_id = UUID("123e4567-e89b-12d3-a456-426614174001")
    refund = _refunded_payment()
    purchase = SimpleNamespace(
        id=purchase_id,
        user_id=77,
        invoice_payload=refund.invoice_payload,
        telegram_payment_charge_id=None,
        status="PRECHECKOUT_OK",
        paid_at=None,
        currency="XTR",
        stars_amount=29,
    )
    calls: list[dict[str, object]] = []

    async def _fake_home_snapshot(session, *, telegram_user):
        del session
        assert telegram_user.id == 270
        return SimpleNamespace(user_id=77)

    async def _fake_get_by_charge_id(_session, telegram_payment_charge_id: str):
        assert telegram_payment_charge_id == refund.telegram_payment_charge_id
        return None

    async def _fake_get_by_invoice_payload(_session, invoice_payload: str):
        assert invoice_payload == refund.invoice_payload
        return purchase

    async def _fake_refund_purchase(
        _session,
        *,
        purchase_id: UUID,
        now_utc: datetime,
        provider_refund_confirmed: bool,
    ):
        assert purchase.status == "PAID_UNCREDITED"
        assert purchase.telegram_payment_charge_id == refund.telegram_payment_charge_id
        assert purchase.paid_at == now_utc
        calls.append(
            {
                "purchase_id": purchase_id,
                "now_utc": now_utc,
                "provider_refund_confirmed": provider_refund_confirmed,
            }
        )
        return SimpleNamespace(status="REFUNDED")

    monkeypatch.setattr(payments_runtime, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(
        payments_runtime.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_home_snapshot,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_telegram_payment_charge_id_for_update",
        _fake_get_by_charge_id,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    result = await payments_runtime.refund_payment_update(
        telegram_user=SimpleNamespace(id=270),  # type: ignore[arg-type]
        refunded_payment=refund,  # type: ignore[arg-type]
        now_utc=now_utc,
    )

    assert result.status == "REFUNDED"
    assert calls == [
        {
            "purchase_id": purchase_id,
            "now_utc": now_utc,
            "provider_refund_confirmed": True,
        }
    ]


@pytest.mark.asyncio
async def test_refund_payment_update_rejects_invoice_fallback_charge_conflict(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    refund = _refunded_payment()
    purchase = SimpleNamespace(
        id=UUID("123e4567-e89b-12d3-a456-426614174002"),
        user_id=77,
        invoice_payload=refund.invoice_payload,
        telegram_payment_charge_id="other-charge",
        status="PAID_UNCREDITED",
        paid_at=now_utc,
        currency="XTR",
        stars_amount=29,
    )

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=77)

    async def _fake_get_by_charge_id(_session, _telegram_payment_charge_id: str):
        return None

    async def _fake_get_by_invoice_payload(_session, _invoice_payload: str):
        return purchase

    async def _fake_refund_purchase(*_args, **_kwargs):
        raise AssertionError("charge conflicts must not reach refund_purchase")

    monkeypatch.setattr(payments_runtime, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(
        payments_runtime.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_home_snapshot,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_telegram_payment_charge_id_for_update",
        _fake_get_by_charge_id,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    with pytest.raises(PurchaseRefundValidationError):
        await payments_runtime.refund_payment_update(
            telegram_user=SimpleNamespace(id=270),  # type: ignore[arg-type]
            refunded_payment=refund,  # type: ignore[arg-type]
            now_utc=now_utc,
        )


@pytest.mark.asyncio
async def test_refund_payment_update_rejects_currency_mismatch_without_mutation(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    refund = _refunded_payment(currency="USD")
    purchase = SimpleNamespace(
        id=UUID("123e4567-e89b-12d3-a456-426614174003"),
        user_id=77,
        invoice_payload=refund.invoice_payload,
        telegram_payment_charge_id=None,
        status="PRECHECKOUT_OK",
        paid_at=None,
        currency="XTR",
        stars_amount=29,
    )

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=77)

    async def _fake_get_by_charge_id(_session, _telegram_payment_charge_id: str):
        return purchase

    async def _fake_refund_purchase(*_args, **_kwargs):
        raise AssertionError("currency mismatch must not reach refund_purchase")

    monkeypatch.setattr(payments_runtime, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(
        payments_runtime.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_home_snapshot,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_telegram_payment_charge_id_for_update",
        _fake_get_by_charge_id,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    with pytest.raises(PurchaseRefundValidationError):
        await payments_runtime.refund_payment_update(
            telegram_user=SimpleNamespace(id=270),  # type: ignore[arg-type]
            refunded_payment=refund,  # type: ignore[arg-type]
            now_utc=now_utc,
        )

    assert purchase.status == "PRECHECKOUT_OK"
    assert purchase.telegram_payment_charge_id is None
    assert purchase.paid_at is None


@pytest.mark.asyncio
async def test_refund_payment_update_rejects_amount_mismatch_without_mutation(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    refund = _refunded_payment(total_amount=30)
    purchase = SimpleNamespace(
        id=UUID("123e4567-e89b-12d3-a456-426614174004"),
        user_id=77,
        invoice_payload=refund.invoice_payload,
        telegram_payment_charge_id=None,
        status="PRECHECKOUT_OK",
        paid_at=None,
        currency="XTR",
        stars_amount=29,
    )

    async def _fake_home_snapshot(session, *, telegram_user):
        del session, telegram_user
        return SimpleNamespace(user_id=77)

    async def _fake_get_by_charge_id(_session, _telegram_payment_charge_id: str):
        return purchase

    async def _fake_refund_purchase(*_args, **_kwargs):
        raise AssertionError("amount mismatch must not reach refund_purchase")

    monkeypatch.setattr(payments_runtime, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(
        payments_runtime.UserOnboardingService,
        "ensure_home_snapshot",
        _fake_home_snapshot,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "get_by_telegram_payment_charge_id_for_update",
        _fake_get_by_charge_id,
    )
    monkeypatch.setattr(
        payments_runtime.PurchaseService,
        "refund_purchase",
        _fake_refund_purchase,
    )

    with pytest.raises(PurchaseRefundValidationError):
        await payments_runtime.refund_payment_update(
            telegram_user=SimpleNamespace(id=270),  # type: ignore[arg-type]
            refunded_payment=refund,  # type: ignore[arg-type]
            now_utc=now_utc,
        )

    assert purchase.status == "PRECHECKOUT_OK"
    assert purchase.telegram_payment_charge_id is None
    assert purchase.paid_at is None
