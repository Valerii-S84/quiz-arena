from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.db.models.entitlements import Entitlement
from app.db.models.purchases import Purchase
from app.db.models.users import User


@dataclass(frozen=True)
class PurchasesQueryRows:
    total: int
    purchase_rows: list[tuple[Purchase, str | None]]
    revenue_by_product_rows: list[tuple[str, int]]


async def fetch_purchase_rows(
    session: AsyncSession,
    *,
    filters: list[ColumnElement[bool]],
    page: int,
    limit: int,
) -> PurchasesQueryRows:
    total_stmt = select(func.count(Purchase.id)).where(and_(*filters))
    total = int((await session.execute(total_stmt)).scalar_one() or 0)

    query_stmt = (
        select(Purchase, User.username)
        .join(User, User.id == Purchase.user_id)
        .where(and_(*filters))
        .order_by(Purchase.paid_at.desc().nullslast(), Purchase.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    purchase_rows = (await session.execute(query_stmt)).all()

    revenue_by_product_stmt = (
        select(Purchase.product_code, func.coalesce(func.sum(Purchase.stars_amount), 0))
        .where(and_(*filters))
        .group_by(Purchase.product_code)
        .order_by(func.coalesce(func.sum(Purchase.stars_amount), 0).desc())
    )
    revenue_by_product_rows = (await session.execute(revenue_by_product_stmt)).all()

    return PurchasesQueryRows(
        total=total,
        purchase_rows=[(purchase, username) for purchase, username in purchase_rows],
        revenue_by_product_rows=[
            (str(product_code), int(total_stars))
            for product_code, total_stars in revenue_by_product_rows
        ],
    )


async def fetch_subscription_rows(
    session: AsyncSession,
    *,
    status: str,
) -> list[tuple[Entitlement, str | None]]:
    stmt = (
        select(Entitlement, User.username)
        .join(User, User.id == Entitlement.user_id)
        .where(Entitlement.entitlement_type == "PREMIUM", Entitlement.status == status)
        .order_by(Entitlement.created_at.desc())
        .limit(500)
    )
    rows = (await session.execute(stmt)).all()
    return [(entitlement, username) for entitlement, username in rows]


@dataclass(frozen=True)
class CohortQueryRows:
    user_rows: list[tuple[int, datetime]]
    purchase_rows: list[tuple[int, datetime | None]]


async def fetch_cohort_rows(
    session: AsyncSession,
    *,
    from_utc: datetime,
) -> CohortQueryRows:
    user_rows = (
        await session.execute(select(User.id, User.created_at).where(User.created_at >= from_utc))
    ).all()
    purchase_rows = (
        await session.execute(
            select(Purchase.user_id, Purchase.paid_at).where(
                Purchase.paid_at.is_not(None),
                Purchase.status.in_(("PAID_UNCREDITED", "CREDITED")),
            )
        )
    ).all()

    return CohortQueryRows(
        user_rows=[(int(uid), created_at) for uid, created_at in user_rows],
        purchase_rows=[(int(uid), paid_at) for uid, paid_at in purchase_rows],
    )
