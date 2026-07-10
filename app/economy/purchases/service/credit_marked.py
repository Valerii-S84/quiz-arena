from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.economy.purchases.catalog import ProductSpec

from .credit_assets import credit_purchase_assets
from .credit_logging import log_credit_failed, log_credit_finished, log_credit_started


async def credit_marked_purchase_assets(
    session: AsyncSession,
    *,
    purchase,
    user_id: int,
    product: ProductSpec,
    telegram_payment_charge_id: str,
    now_utc: datetime,
) -> None:
    log_credit_started(purchase=purchase, user_id=user_id, product_code=product.product_code)
    try:
        await credit_purchase_assets(
            session,
            user_id=user_id,
            purchase=purchase,
            product=product,
            now_utc=now_utc,
        )
    except Exception as exc:
        # Re-raise to preserve rollback behavior while making failed credit attempts visible.
        log_credit_failed(
            purchase=purchase,
            user_id=user_id,
            product_code=product.product_code,
            error_type=type(exc).__name__,
        )
        raise
    log_credit_finished(
        purchase=purchase,
        user_id=user_id,
        product_code=product.product_code,
        telegram_payment_charge_id=telegram_payment_charge_id,
    )
