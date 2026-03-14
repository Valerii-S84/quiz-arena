from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.economy.purchases.service.credit as purchase_credit
from app.economy.purchases.catalog import ProductSpec
from app.economy.purchases.errors import (
    ProductNotFoundError,
    PurchaseNotFoundError,
    PurchasePrecheckoutValidationError,
)

UTC = timezone.utc


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
            object(),
            user_id=7,
            invoice_payload="inv-missing",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment={"invoice_payload": "inv-missing"},
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
            object(),
            user_id=7,
            invoice_payload="inv-failed",
            telegram_payment_charge_id="charge-1",
            raw_successful_payment={"invoice_payload": "inv-failed"},
            now_utc=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_apply_zero_cost_purchase_replays_already_credited_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase(status="CREDITED", stars_amount=0)

    async def _fake_get_by_id_for_update(_session, _purchase_id):
        return purchase

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )

    result = await purchase_credit.apply_zero_cost_purchase(
        object(),
        purchase_id=purchase.id,
        user_id=7,
        now_utc=datetime.now(UTC),
    )

    assert result.purchase_id == purchase.id
    assert result.product_code == "ENERGY_10"
    assert result.status == "CREDITED"
    assert result.idempotent_replay is True


@pytest.mark.asyncio
async def test_apply_zero_cost_purchase_rejects_non_zero_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase(status="CREATED", stars_amount=5)

    async def _fake_get_by_id_for_update(_session, _purchase_id):
        return purchase

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_credit.apply_zero_cost_purchase(
            object(),
            purchase_id=purchase.id,
            user_id=7,
            now_utc=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_apply_zero_cost_purchase_rejects_invalid_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase(status="FAILED", stars_amount=0)

    async def _fake_get_by_id_for_update(_session, _purchase_id):
        return purchase

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )

    with pytest.raises(PurchasePrecheckoutValidationError):
        await purchase_credit.apply_zero_cost_purchase(
            object(),
            purchase_id=purchase.id,
            user_id=7,
            now_utc=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_apply_zero_cost_purchase_rejects_missing_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purchase = _purchase(status="CREATED", stars_amount=0)
    emitted_events: list[dict[str, object]] = []

    async def _fake_get_by_id_for_update(_session, _purchase_id):
        return purchase

    async def _fake_emit_purchase_event(
        _session,
        *,
        event_type: str,
        purchase,
        happened_at: datetime,
        extra_payload: dict[str, object],
    ) -> None:
        emitted_events.append(
            {
                "event_type": event_type,
                "purchase_id": purchase.id,
                "happened_at": happened_at,
                "extra_payload": extra_payload,
            }
        )

    monkeypatch.setattr(
        purchase_credit.PurchasesRepo,
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )
    monkeypatch.setattr(purchase_credit, "_emit_purchase_event", _fake_emit_purchase_event)
    monkeypatch.setattr(purchase_credit, "get_product", lambda _product_code: None)

    with pytest.raises(ProductNotFoundError):
        await purchase_credit.apply_zero_cost_purchase(
            object(),
            purchase_id=purchase.id,
            user_id=7,
            now_utc=datetime.now(UTC),
        )

    assert emitted_events[0]["event_type"] == "purchase_paid_uncredited"
    assert emitted_events[0]["extra_payload"] == {"previous_status": "CREATED", "zero_cost": True}


@pytest.mark.asyncio
async def test_apply_zero_cost_purchase_marks_paid_and_credits_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    purchase = _purchase(status="CREATED", stars_amount=0)
    events: list[str] = []
    credit_calls: list[dict[str, object]] = []
    product = ProductSpec(
        product_code="ENERGY_10",
        product_type="MICRO",
        title="Energy",
        description="Energy",
        stars_amount=0,
        energy_credit=10,
    )

    async def _fake_get_by_id_for_update(_session, _purchase_id):
        return purchase

    async def _fake_emit_purchase_event(
        _session,
        *,
        event_type: str,
        purchase,
        happened_at: datetime,
        extra_payload: dict[str, object],
    ) -> None:
        assert purchase.id == purchase.id
        assert happened_at == now_utc
        assert extra_payload["zero_cost"] is True
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
        "get_by_id_for_update",
        _fake_get_by_id_for_update,
    )
    monkeypatch.setattr(purchase_credit, "_emit_purchase_event", _fake_emit_purchase_event)
    monkeypatch.setattr(purchase_credit, "credit_purchase_assets", _fake_credit_purchase_assets)
    monkeypatch.setattr(purchase_credit, "get_product", lambda _product_code: product)

    result = await purchase_credit.apply_zero_cost_purchase(
        object(),
        purchase_id=purchase.id,
        user_id=7,
        now_utc=now_utc,
    )

    assert purchase.paid_at == now_utc
    assert events == ["purchase_paid_uncredited"]
    assert credit_calls == [
        {
            "user_id": 7,
            "purchase_id": purchase.id,
            "product_code": "ENERGY_10",
            "now_utc": now_utc,
        }
    ]
    assert result.purchase_id == purchase.id
    assert result.status == "CREDITED"
    assert result.idempotent_replay is False
