from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.purchases import Purchase

from .purchases_repo_metrics import (
    count_by_user,
    count_credited_premium_without_entitlement,
    count_credited_product,
    count_credited_stars_without_purchase_credit,
    count_paid_product_since,
    count_paid_purchases,
    count_paid_purchases_for_user,
    count_paid_uncredited_older_than,
    count_precheckout_ok_older_than,
    sum_paid_stars_amount,
    sum_paid_stars_amount_by_product,
)
from .purchases_repo_reconciliation import list_stars_reconciliation_candidate_rows
from .purchases_repo_writes import create, expire_stale_unpaid_invoices


class PurchasesRepo:
    count_paid_purchases = staticmethod(count_paid_purchases)
    sum_paid_stars_amount = staticmethod(sum_paid_stars_amount)
    sum_paid_stars_amount_by_product = staticmethod(sum_paid_stars_amount_by_product)
    count_by_user = staticmethod(count_by_user)
    count_paid_purchases_for_user = staticmethod(count_paid_purchases_for_user)
    count_paid_product_since = staticmethod(count_paid_product_since)
    count_credited_product = staticmethod(count_credited_product)
    count_paid_uncredited_older_than = staticmethod(count_paid_uncredited_older_than)
    count_precheckout_ok_older_than = staticmethod(count_precheckout_ok_older_than)
    count_credited_premium_without_entitlement = staticmethod(
        count_credited_premium_without_entitlement
    )
    count_credited_stars_without_purchase_credit = staticmethod(
        count_credited_stars_without_purchase_credit
    )
    list_stars_reconciliation_candidate_rows = staticmethod(
        list_stars_reconciliation_candidate_rows
    )
    expire_stale_unpaid_invoices = staticmethod(expire_stale_unpaid_invoices)
    create = staticmethod(create)

    @staticmethod
    async def get_by_id(session: AsyncSession, purchase_id: UUID) -> Purchase | None:
        return await session.get(Purchase, purchase_id)

    @staticmethod
    async def get_by_id_for_update(session: AsyncSession, purchase_id: UUID) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.id == purchase_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_idempotency_key(
        session: AsyncSession, idempotency_key: str
    ) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.idempotency_key == idempotency_key)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_invoice_payload(
        session: AsyncSession, invoice_payload: str
    ) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.invoice_payload == invoice_payload)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_invoice_payload_for_update(
        session: AsyncSession, invoice_payload: str
    ) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.invoice_payload == invoice_payload).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_telegram_payment_charge_id_for_update(
        session: AsyncSession,
        telegram_payment_charge_id: str,
    ) -> Purchase | None:
        stmt = (
            select(Purchase)
            .where(Purchase.telegram_payment_charge_id == telegram_payment_charge_id)
            .with_for_update()
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_invoice_for_user_product(
        session: AsyncSession,
        *,
        user_id: int,
        product_code: str,
    ) -> Purchase | None:
        stmt = (
            select(Purchase)
            .where(
                Purchase.user_id == user_id,
                Purchase.product_code == product_code,
                Purchase.status.in_(("CREATED", "INVOICE_SENT", "PRECHECKOUT_OK")),
            )
            .order_by(Purchase.created_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_invoice_for_user_product_for_update(
        session: AsyncSession,
        *,
        user_id: int,
        product_code: str,
    ) -> Purchase | None:
        stmt = (
            select(Purchase)
            .where(
                Purchase.user_id == user_id,
                Purchase.product_code == product_code,
                Purchase.status.in_(("CREATED", "INVOICE_SENT", "PRECHECKOUT_OK")),
            )
            .order_by(Purchase.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_for_credit_lock(session: AsyncSession, purchase_id: UUID) -> Purchase | None:
        stmt = select(Purchase).where(Purchase.id == purchase_id).with_for_update()
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_paid_uncredited_older_than(
        session: AsyncSession,
        *,
        older_than_utc: datetime,
        limit: int = 100,
    ) -> list[Purchase]:
        stmt = (
            select(Purchase)
            .where(
                Purchase.status == "PAID_UNCREDITED",
                Purchase.paid_at.is_not(None),
                Purchase.paid_at <= older_than_utc,
            )
            .order_by(Purchase.paid_at.asc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
