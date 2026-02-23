from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.db.models.purchases import Purchase
from app.economy.purchases.catalog import ProductSpec
from app.economy.purchases.types import PurchaseInitResult

from .utilities import _build_invoice_payload


def _build_purchase(
    product: ProductSpec,
    *,
    user_id: int,
    idempotency_key: str,
    discount_stars_amount: int,
    applied_promo_code_id: int | None,
    now_utc: datetime,
) -> Purchase:
    final_stars_amount = max(1, product.stars_amount - discount_stars_amount)
    return Purchase(
        id=uuid4(),
        user_id=user_id,
        product_code=product.product_code,
        product_type=product.product_type,
        base_stars_amount=product.stars_amount,
        discount_stars_amount=discount_stars_amount,
        stars_amount=final_stars_amount,
        currency="XTR",
        status="CREATED",
        applied_promo_code_id=applied_promo_code_id,
        idempotency_key=idempotency_key,
        invoice_payload=_build_invoice_payload(),
        created_at=now_utc,
    )


def _as_init_result(purchase: Purchase, *, idempotent_replay: bool) -> PurchaseInitResult:
    return PurchaseInitResult(
        purchase_id=purchase.id,
        invoice_payload=purchase.invoice_payload,
        product_code=purchase.product_code,
        final_stars_amount=purchase.stars_amount,
        base_stars_amount=purchase.base_stars_amount,
        discount_stars_amount=purchase.discount_stars_amount,
        applied_promo_code_id=purchase.applied_promo_code_id,
        idempotent_replay=idempotent_replay,
    )
