from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.models.purchases import Purchase
from app.db.models.users import User

from .purchases_repo_metrics import (
    count_paid_purchases,
    sum_paid_stars_amount,
    sum_paid_stars_amount_by_product,
)


class PurchasesRepo:
    count_paid_purchases = staticmethod(count_paid_purchases)
    sum_paid_stars_amount = staticmethod(sum_paid_stars_amount)
    sum_paid_stars_amount_by_product = staticmethod(sum_paid_stars_amount_by_product)

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

    @staticmethod
    async def count_by_user(session: AsyncSession, *, user_id: int) -> int:
        stmt = select(func.count(Purchase.id)).where(Purchase.user_id == user_id)
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_paid_purchases_for_user(session: AsyncSession, *, user_id: int) -> int:
        stmt = select(func.count(Purchase.id)).where(
            Purchase.user_id == user_id,
            Purchase.paid_at.is_not(None),
            Purchase.stars_amount > 0,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_paid_product_since(
        session: AsyncSession,
        *,
        user_id: int,
        product_code: str,
        since_utc: datetime,
    ) -> int:
        stmt = select(func.count(Purchase.id)).where(
            Purchase.user_id == user_id,
            Purchase.product_code == product_code,
            Purchase.paid_at.is_not(None),
            Purchase.paid_at >= since_utc,
            Purchase.stars_amount > 0,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_credited_product(
        session: AsyncSession,
        *,
        user_id: int,
        product_code: str,
    ) -> int:
        stmt = select(func.count(Purchase.id)).where(
            Purchase.user_id == user_id,
            Purchase.product_code == product_code,
            Purchase.status == "CREDITED",
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_paid_uncredited_older_than(
        session: AsyncSession,
        *,
        older_than_utc: datetime,
    ) -> int:
        stmt = select(func.count(Purchase.id)).where(
            Purchase.status == "PAID_UNCREDITED",
            Purchase.paid_at.is_not(None),
            Purchase.paid_at <= older_than_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_precheckout_ok_older_than(
        session: AsyncSession,
        *,
        older_than_utc: datetime,
    ) -> int:
        stmt = select(func.count(Purchase.id)).where(
            Purchase.status == "PRECHECKOUT_OK",
            Purchase.stars_amount > 0,
            Purchase.created_at <= older_than_utc,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_credited_premium_without_entitlement(session: AsyncSession) -> int:
        entitlement_exists = (
            select(Entitlement.id)
            .where(
                Entitlement.source_purchase_id == Purchase.id,
                Entitlement.entitlement_type == "PREMIUM",
            )
            .exists()
        )
        stmt = select(func.count(Purchase.id)).where(
            Purchase.status == "CREDITED",
            Purchase.product_type == "PREMIUM",
            ~entitlement_exists,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def count_credited_stars_without_purchase_credit(session: AsyncSession) -> int:
        ledger_exists = (
            select(LedgerEntry.id)
            .where(
                LedgerEntry.purchase_id == Purchase.id,
                LedgerEntry.entry_type == "PURCHASE_CREDIT",
                LedgerEntry.direction == "CREDIT",
            )
            .exists()
        )
        stmt = select(func.count(Purchase.id)).where(
            Purchase.status == "CREDITED",
            Purchase.stars_amount > 0,
            ~ledger_exists,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def list_stars_reconciliation_candidate_rows(
        session: AsyncSession,
        *,
        transaction_id: str,
        invoice_payload: str | None,
        telegram_user_id: int | None,
        transaction_date: datetime,
        match_window: timedelta,
        limit: int = 20,
    ) -> list[tuple[Purchase, int]]:
        match_conditions = [Purchase.telegram_payment_charge_id == transaction_id]
        if invoice_payload:
            match_conditions.append(Purchase.invoice_payload == invoice_payload)
        if telegram_user_id is not None:
            match_conditions.append(
                and_(
                    User.telegram_user_id == telegram_user_id,
                    Purchase.created_at >= transaction_date - match_window,
                    Purchase.created_at <= transaction_date,
                )
            )

        stmt = (
            select(Purchase, User.telegram_user_id)
            .join(User, User.id == Purchase.user_id)
            .where(Purchase.stars_amount > 0, or_(*match_conditions))
            .order_by(Purchase.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [(cast(Purchase, row[0]), int(row[1])) for row in result.all()]

    @staticmethod
    async def expire_stale_unpaid_invoices(
        session: AsyncSession,
        *,
        older_than_utc: datetime,
    ) -> int:
        stmt = (
            update(Purchase)
            .where(
                Purchase.status.in_(("CREATED", "INVOICE_SENT")),
                Purchase.created_at <= older_than_utc,
                Purchase.paid_at.is_(None),
            )
            .values(status="FAILED")
        )
        result = await session.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        purchase: Purchase,
        created_at: datetime,
    ) -> Purchase:
        purchase.created_at = created_at
        session.add(purchase)
        await session.flush()
        return purchase
