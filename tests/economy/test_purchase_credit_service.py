from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.economy.purchases.service.credit as purchase_credit
from app.economy.purchases.catalog import ProductSpec
from app.economy.purchases.errors import PurchaseNotFoundError, PurchasePrecheckoutValidationError
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc


class _Session(AsyncSessionStub):
    pass


class _Logger:
    def __init__(self) -> None:
        self.infos: list[tuple[str, dict[str, object]]] = []
        self.warnings: list[tuple[str, dict[str, object]]] = []

    def info(self, event: str, **payload: object) -> None:
        self.infos.append((event, payload))

    def warning(self, event: str, **payload: object) -> None:
        self.warnings.append((event, payload))


def _purchase(
    *, user_id: int = 7, status: str = "CREATED", stars_amount: int = 0
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        status=status,
        product_code="ENERGY_10",
        stars_amount=stars_amount,
        paid_at=None,
        telegram_payment_charge_id=None,
        raw_successful_payment=None,
    )


def _successful_payment_payload(
    invoice_payload: str, *, total_amount: int = 5
) -> dict[str, object]:
    return {
        "invoice_payload": invoice_payload,
        "currency": "XTR",
        "total_amount": total_amount,
    }


@pytest.mark.asyncio
async def test_apply_successful_payment_rejects_missing_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload):
        return None

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )

    with pytest.raises(PurchaseNotFoundError):
        await purchase_credit.apply_successful_payment(
            _Session(),
            user_id=7,
            invoice_payload="inv-missing",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment={"invoice_payload": "inv-missing"},
            now_utc=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_apply_successful_payment_rejects_purchase_owned_by_different_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase(user_id=8, status="INVOICE_SENT", stars_amount=5)

    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload):
        return purchase

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )

    with pytest.raises(PurchaseNotFoundError):
        await purchase_credit.apply_successful_payment(
            _Session(),
            user_id=7,
            invoice_payload="inv-other-user",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment={
                "invoice_payload": "inv-other-user",
                "currency": "XTR",
                "total_amount": 5,
            },
            now_utc=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_apply_successful_payment_rejects_invalid_purchase_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase(status="FAILED", stars_amount=5)

    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload):
        return purchase

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_credit.apply_successful_payment(
            _Session(),
            user_id=7,
            invoice_payload="inv-failed",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment={"invoice_payload": "inv-failed"},
            now_utc=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_apply_successful_payment_credits_legacy_premium_starter_as_premium_week(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    purchase = _purchase(status="INVOICE_SENT", stars_amount=29)
    purchase.product_code = "PREMIUM_STARTER"
    events: list[str] = []
    credit_calls: list[dict[str, object]] = []
    logger = _Logger()

    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload):
        return purchase

    async def _fake_emit_purchase_event(
        _session,
        *,
        event_type: str,
        purchase,
        happened_at: datetime,
        extra_payload: dict[str, object],
    ) -> None:
        del purchase, happened_at, extra_payload
        events.append(event_type)

    async def _fake_credit_purchase_assets(
        _session, *, user_id: int, purchase, product: ProductSpec, now_utc: datetime
    ) -> None:
        credit_calls.append(
            {
                "user_id": user_id,
                "purchase_id": purchase.id,
                "product_code": product.product_code,
                "now_utc": now_utc,
            }
        )
        purchase.status = "CREDITED"

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )
    monkeypatch.setattr(purchase_credit, "_emit_purchase_event", _fake_emit_purchase_event)
    monkeypatch.setattr(purchase_credit, "credit_purchase_assets", _fake_credit_purchase_assets)
    monkeypatch.setattr(purchase_credit, "logger", logger)

    result = await purchase_credit.apply_successful_payment(
        _Session(),
        user_id=7,
        invoice_payload="inv-starter",
        telegram_payment_charge_id="charge-1",
        raw_successful_payment={
            "invoice_payload": "inv-starter",
            "currency": "XTR",
            "total_amount": 29,
        },
        now_utc=now_utc,
    )

    assert purchase.paid_at == now_utc
    assert events == ["purchase_paid_uncredited"]
    assert credit_calls == [
        {
            "user_id": 7,
            "purchase_id": purchase.id,
            "product_code": "PREMIUM_WEEK",
            "now_utc": now_utc,
        }
    ]
    assert result.purchase_id == purchase.id
    assert result.product_code == "PREMIUM_WEEK"
    assert result.status == "CREDITED"
    assert result.idempotent_replay is False
    assert [event for event, _payload in logger.infos] == [
        "payment_successful_mark_paid_started",
        "payment_successful_mark_paid_finished",
        "payment_credit_started",
        "payment_credit_finished",
    ]
    for _event, payload in logger.infos:
        assert payload["telegram_payment_charge_id_hash"] != "charge-1"
        assert "telegram_payment_charge_id" not in payload
    assert "inv-starter" not in str(logger.infos)
    assert "charge-1" not in str(logger.infos)


@pytest.mark.asyncio
async def test_apply_successful_payment_logs_credit_failure_without_raw_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    purchase = _purchase(status="INVOICE_SENT", stars_amount=5)
    logger = _Logger()

    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload):
        return purchase

    async def _fake_emit_purchase_event(*_args, **_kwargs) -> None:
        return None

    async def _fail_credit_purchase_assets(*_args, **_kwargs) -> None:
        raise RuntimeError("credit_failed")

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )
    monkeypatch.setattr(purchase_credit, "_emit_purchase_event", _fake_emit_purchase_event)
    monkeypatch.setattr(purchase_credit, "credit_purchase_assets", _fail_credit_purchase_assets)
    monkeypatch.setattr(purchase_credit, "logger", logger)

    with pytest.raises(RuntimeError):
        await purchase_credit.apply_successful_payment(
            _Session(),
            user_id=7,
            invoice_payload="inv-failure",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment=_successful_payment_payload("inv-failure"),
            now_utc=now_utc,
        )

    event, payload = logger.warnings[0]
    assert event == "payment_credit_failed"
    assert payload["purchase_id"] == str(purchase.id)
    assert payload["status"] == "PAID_UNCREDITED"
    assert payload["telegram_payment_charge_id_hash"] != "charge-1"
    assert "telegram_payment_charge_id" not in payload
    assert payload["error_type"] == "RuntimeError"
    assert "inv-failure" not in str(logger.infos + logger.warnings)
    assert "charge-1" not in str(logger.infos + logger.warnings)
    assert "token" not in str(logger.infos + logger.warnings).lower()


@pytest.mark.asyncio
async def test_apply_successful_payment_rejects_non_xtr_currency_for_paid_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase(status="INVOICE_SENT", stars_amount=5)

    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload):
        return purchase

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_credit.apply_successful_payment(
            _Session(),
            user_id=7,
            invoice_payload="inv-wrong-currency",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment={
                "invoice_payload": "inv-wrong-currency",
                "currency": "USD",
                "total_amount": 5,
            },
            now_utc=datetime.now(UTC),
        )

    assert purchase.status == "INVOICE_SENT"
    assert purchase.raw_successful_payment is None


@pytest.mark.asyncio
async def test_apply_successful_payment_rejects_mismatched_total_amount_for_paid_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase(status="INVOICE_SENT", stars_amount=5)

    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload):
        return purchase

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_credit.apply_successful_payment(
            _Session(),
            user_id=7,
            invoice_payload="inv-wrong-total",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment={
                "invoice_payload": "inv-wrong-total",
                "currency": "XTR",
                "total_amount": 6,
            },
            now_utc=datetime.now(UTC),
        )

    assert purchase.status == "INVOICE_SENT"
    assert purchase.raw_successful_payment is None


@pytest.mark.asyncio
async def test_apply_successful_payment_rejects_missing_payment_payload_for_paid_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase(status="INVOICE_SENT", stars_amount=5)

    async def _fake_get_by_invoice_payload_for_update(_session, _invoice_payload):
        return purchase

    async def _fail_credit_purchase_assets(*_args, **_kwargs) -> None:
        pytest.fail("paid purchase without successful payment payload must not be credited")

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_invoice_payload_for_update",
        _fake_get_by_invoice_payload_for_update,
    )
    monkeypatch.setattr(purchase_credit, "credit_purchase_assets", _fail_credit_purchase_assets)

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_credit.apply_successful_payment(
            _Session(),
            user_id=7,
            invoice_payload="inv-missing-payment",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment={},
            now_utc=datetime.now(UTC),
        )

    assert purchase.status == "INVOICE_SENT"
    assert purchase.telegram_payment_charge_id is None
    assert purchase.raw_successful_payment is None
