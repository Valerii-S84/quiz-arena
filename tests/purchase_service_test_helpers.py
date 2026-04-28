from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Sequence
from uuid import UUID, uuid4

from app.db.models.purchases import Purchase
from app.economy.purchases.catalog import ProductSpec
from tests.type_helpers import AsyncSessionStub, build_promo_code

UTC = timezone.utc
NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


class SessionStub(AsyncSessionStub):
    def __init__(self) -> None:
        self.flush_calls = 0

    async def flush(self, objects: Sequence[Any] | None = None) -> None:
        del objects
        self.flush_calls += 1


def product_spec() -> ProductSpec:
    return ProductSpec(
        product_code="ENERGY_10",
        product_type="MICRO",
        title="Energy",
        description="Energy",
        stars_amount=5,
        energy_credit=10,
    )


def promo_code(**overrides: object):
    payload: dict[str, object] = {
        "id": 21,
        "discount_type": "PERCENT",
        "discount_value": 50,
        "discount_percent": None,
        "target_scope": "ANY",
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=1),
        "max_total_uses": 10,
        "used_total": 0,
    }
    payload.update(overrides)
    return build_promo_code(**payload)


def purchase_model(
    *,
    purchase_id: UUID | None = None,
    user_id: int = 7,
    product_code: str = "ENERGY_10",
    product_type: str = "MICRO",
    base_stars_amount: int = 5,
    discount_stars_amount: int = 0,
    stars_amount: int = 5,
    status: str = "CREATED",
    applied_promo_code_id: int | None = None,
    idempotency_key: str = "idem-existing",
    invoice_payload: str = "inv_existing",
) -> Purchase:
    return Purchase(
        id=purchase_id or uuid4(),
        user_id=user_id,
        product_code=product_code,
        product_type=product_type,
        base_stars_amount=base_stars_amount,
        discount_stars_amount=discount_stars_amount,
        stars_amount=stars_amount,
        currency="XTR",
        status=status,
        applied_promo_code_id=applied_promo_code_id,
        idempotency_key=idempotency_key,
        invoice_payload=invoice_payload,
        created_at=NOW,
    )


def refund_purchase_state(*, status: str = "CREDITED"):
    return SimpleNamespace(
        id=uuid4(),
        user_id=7,
        product_code="ENERGY_10",
        status=status,
        refunded_at=None,
    )


def credit_entry(*, purchase_id: UUID, metadata: dict[str, object] | None = None):
    return SimpleNamespace(
        purchase_id=purchase_id,
        asset="PURCHASE",
        amount=5,
        idempotency_key=f"credit:purchase:{purchase_id}",
        metadata_=metadata
        or {
            "product_code": "ENERGY_10",
            "asset_breakdown": {"paid_energy": 10},
        },
    )
