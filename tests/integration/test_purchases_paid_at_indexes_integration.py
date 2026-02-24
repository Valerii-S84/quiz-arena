from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import insert, text

from app.db.models.purchases import Purchase
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal

UTC = timezone.utc


async def _create_user_id(seed: int) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=90_000_000_000 + seed,
            referral_code=f"P{uuid4().hex[:10].upper()}",
            username=None,
            first_name="PurchasesPerf",
            referred_by_user_id=None,
        )
        return int(user.id)


def _build_purchase_row(
    *,
    user_id: int,
    idx: int,
    status: str,
    paid_at: datetime | None,
    stars_amount: int,
    now_utc: datetime,
) -> dict[str, object]:
    return {
        "id": uuid4(),
        "user_id": user_id,
        "product_code": "ENERGY_10",
        "product_type": "MICRO",
        "base_stars_amount": stars_amount,
        "discount_stars_amount": 0,
        "stars_amount": stars_amount,
        "currency": "XTR",
        "status": status,
        "applied_promo_code_id": None,
        "idempotency_key": f"paid-at-index:test:{idx}",
        "invoice_payload": f"paid-at-index:invoice:{idx}",
        "telegram_payment_charge_id": None,
        "telegram_pre_checkout_query_id": None,
        "raw_successful_payment": None,
        "created_at": now_utc - timedelta(days=2),
        "paid_at": paid_at,
        "credited_at": now_utc if status == "CREDITED" else None,
        "refunded_at": None,
    }


def _assert_index_plan(plan_text: str, *, index_name: str) -> None:
    assert (
        "Index Scan" in plan_text
        or "Bitmap Index Scan" in plan_text
        or "Index Only Scan" in plan_text
    )
    assert index_name in plan_text


@pytest.mark.asyncio
async def test_paid_at_aggregate_queries_use_paid_at_index() -> None:
    now_utc = datetime(2026, 2, 20, 10, 0, tzinfo=UTC)
    user_id = await _create_user_id(1)

    rows: list[dict[str, object]] = []
    for idx in range(5_000):
        rows.append(
            _build_purchase_row(
                user_id=user_id,
                idx=idx,
                status="FAILED",
                paid_at=None,
                stars_amount=10,
                now_utc=now_utc,
            )
        )
    for idx in range(5_000, 5_500):
        rows.append(
            _build_purchase_row(
                user_id=user_id,
                idx=idx,
                status="CREDITED",
                paid_at=now_utc - timedelta(minutes=idx - 5_000 + 1),
                stars_amount=15,
                now_utc=now_utc,
            )
        )

    async with SessionLocal.begin() as session:
        await session.execute(insert(Purchase), rows)

    async with SessionLocal.begin() as session:
        await session.execute(text("ANALYZE purchases"))

        count_explain = await session.execute(
            text("EXPLAIN SELECT count(id) FROM purchases WHERE paid_at IS NOT NULL")
        )
        count_plan = "\n".join(str(line) for line in count_explain.scalars().all())
        _assert_index_plan(count_plan, index_name="idx_purchases_paid_at_not_null")

        sum_explain = await session.execute(
            text(
                "EXPLAIN SELECT COALESCE(sum(stars_amount), 0) FROM purchases WHERE paid_at IS NOT NULL"
            )
        )
        sum_plan = "\n".join(str(line) for line in sum_explain.scalars().all())
        _assert_index_plan(sum_plan, index_name="idx_purchases_paid_at_not_null")
