from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.db.models.ledger_entries import LedgerEntry
from app.db.session import SessionLocal
from app.economy.purchases.catalog import MEGA_PACK_MODE_CODES
from app.economy.purchases.service import PurchaseService
from tests.integration.payments_idempotency_fixtures import UTC, _create_user


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("product_code", "expected_breakdown"),
    [
        ("ENERGY_10", {"paid_energy": 10}),
        (
            "MEGA_PACK_15",
            {"paid_energy": 15, "mode_codes": list(MEGA_PACK_MODE_CODES)},
        ),
        ("PREMIUM_MONTH", {"premium_days": 30}),
        ("STREAK_SAVER_20", {"streak_saver_tokens": 1}),
    ],
)
async def test_purchase_credit_is_aggregated_single_ledger_entry(
    product_code: str,
    expected_breakdown: dict[str, object],
) -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user(f"purchase-credit-aggregation:{product_code}")

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code=product_code,
            idempotency_key=f"credit-aggregation:{product_code}:init",
            now_utc=now_utc,
        )
        await PurchaseService.mark_invoice_sent(session, purchase_id=init.purchase_id)
        await PurchaseService.validate_precheckout(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            total_amount=init.final_stars_amount,
            now_utc=now_utc,
        )
        await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id=f"tg_charge_credit_aggregation_{product_code}",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc,
        )

    async with SessionLocal.begin() as session:
        entry_count = await session.scalar(
            select(func.count(LedgerEntry.id)).where(
                LedgerEntry.purchase_id == init.purchase_id,
                LedgerEntry.entry_type == "PURCHASE_CREDIT",
                LedgerEntry.direction == "CREDIT",
            )
        )
        assert int(entry_count or 0) == 1

        entry = await session.scalar(
            select(LedgerEntry).where(
                LedgerEntry.purchase_id == init.purchase_id,
                LedgerEntry.entry_type == "PURCHASE_CREDIT",
                LedgerEntry.direction == "CREDIT",
            )
        )
        assert entry is not None
        assert entry.asset == "PURCHASE"
        assert entry.idempotency_key == f"credit:purchase:{init.purchase_id}"
        assert entry.metadata_["product_code"] == product_code

        breakdown = entry.metadata_["asset_breakdown"]
        assert isinstance(breakdown, dict)
        for key, expected_value in expected_breakdown.items():
            assert breakdown[key] == expected_value
