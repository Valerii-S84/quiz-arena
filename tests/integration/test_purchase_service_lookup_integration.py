from __future__ import annotations

from datetime import datetime

import pytest

from app.db.session import SessionLocal
from app.economy.purchases.service import PurchaseService
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_purchase_service_get_by_id_reads_purchase_from_db() -> None:
    now_utc = datetime(2026, 2, 22, 12, 0, tzinfo=UTC)
    user_id = await _create_user("purchase-service-get-by-id")

    async with SessionLocal.begin() as session:
        init_result = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="buy:integration:get-by-id:1",
            now_utc=now_utc,
        )

    async with SessionLocal.begin() as session:
        purchase = await PurchaseService.get_by_id(session, init_result.purchase_id)

    assert purchase is not None
    assert purchase.id == init_result.purchase_id
    assert purchase.idempotency_key == "buy:integration:get-by-id:1"
