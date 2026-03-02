from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.sql.elements import ColumnElement

from app.api.routes.admin.deps import AdminPrincipal, add_admin_noindex_header, get_current_admin
from app.api.routes.admin.economy_ltv import build_ltv_30d_by_cohort
from app.api.routes.admin.pagination import build_pagination
from app.db.models.entitlements import Entitlement
from app.db.models.purchases import Purchase
from app.db.models.users import User
from app.db.session import SessionLocal

router = APIRouter(prefix="/admin/economy", tags=["admin-economy"])
STAR_TO_EUR_RATE = Decimal("0.02")


class PurchasesResponse(BaseModel):
    items: list[dict[str, object]]
    total: int
    page: int
    pages: int
    charts: dict[str, list[dict[str, object]]]


class SubscriptionsResponse(BaseModel):
    items: list[dict[str, object]]
    total: int


class CohortsResponse(BaseModel):
    week_offsets: list[int]
    cohorts: list[dict[str, object]]


def _parse_datetime(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    parsed = datetime.fromisoformat(raw_value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@router.get("/purchases", response_model=PurchasesResponse)
async def list_purchases(
    response: Response,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    product: str | None = Query(default=None),
    user_id: int | None = Query(default=None, ge=1),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> PurchasesResponse:
    add_admin_noindex_header(response)
    now_utc = datetime.now(timezone.utc)
    from_dt = _parse_datetime(from_)
    to_dt = _parse_datetime(to)

    filters: list[ColumnElement[bool]] = [Purchase.paid_at.is_not(None)]
    if product:
        filters.append(Purchase.product_code == product)
    if user_id is not None:
        filters.append(Purchase.user_id == user_id)
    if from_dt is not None:
        filters.append(Purchase.paid_at >= from_dt)
    if to_dt is not None:
        filters.append(Purchase.paid_at < to_dt)

    async with SessionLocal.begin() as session:
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
        rows = (await session.execute(query_stmt)).all()

        revenue_by_product_stmt = (
            select(Purchase.product_code, func.coalesce(func.sum(Purchase.stars_amount), 0))
            .where(and_(*filters))
            .group_by(Purchase.product_code)
            .order_by(func.coalesce(func.sum(Purchase.stars_amount), 0).desc())
        )
        revenue_by_product = [
            {
                "product": product_code,
                "stars": int(total_stars),
                "eur": float(Decimal(total_stars) * STAR_TO_EUR_RATE),
            }
            for product_code, total_stars in (await session.execute(revenue_by_product_stmt)).all()
        ]

        ltv_30d_by_cohort = await build_ltv_30d_by_cohort(
            session,
            cohort_from_utc=from_dt or (now_utc - timedelta(weeks=12)),
            cohort_to_utc=to_dt or now_utc,
        )

    items = []
    for purchase, username in rows:
        source = "telegram"
        utm = None
        if isinstance(purchase.raw_successful_payment, dict):
            source = str(purchase.raw_successful_payment.get("source") or source)
            utm = purchase.raw_successful_payment.get("utm")
        items.append(
            {
                "id": str(purchase.id),
                "user_id": int(purchase.user_id),
                "username": username,
                "product": purchase.product_code,
                "stars": int(purchase.stars_amount),
                "eur": float(Decimal(purchase.stars_amount) * STAR_TO_EUR_RATE),
                "date": purchase.paid_at.isoformat() if purchase.paid_at else None,
                "source": source,
                "utm": utm,
                "status": purchase.status,
            }
        )

    pagination = build_pagination(total=total, page=page, limit=limit)
    return PurchasesResponse(
        items=items,
        total=pagination["total"],
        page=pagination["page"],
        pages=pagination["pages"],
        charts={
            "revenue_by_product": revenue_by_product,
            "ltv_30d_by_cohort": ltv_30d_by_cohort,
        },
    )


@router.get("/subscriptions", response_model=SubscriptionsResponse)
async def list_subscriptions(
    response: Response,
    status: str = Query(default="ACTIVE"),
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> SubscriptionsResponse:
    add_admin_noindex_header(response)
    async with SessionLocal.begin() as session:
        stmt = (
            select(Entitlement, User.username)
            .join(User, User.id == Entitlement.user_id)
            .where(Entitlement.entitlement_type == "PREMIUM", Entitlement.status == status)
            .order_by(Entitlement.created_at.desc())
            .limit(500)
        )
        rows = (await session.execute(stmt)).all()

    items = [
        {
            "id": int(entitlement.id),
            "user_id": int(entitlement.user_id),
            "username": username,
            "status": entitlement.status,
            "starts_at": entitlement.starts_at.isoformat(),
            "ends_at": entitlement.ends_at.isoformat() if entitlement.ends_at else None,
        }
        for entitlement, username in rows
    ]
    return SubscriptionsResponse(items=items, total=len(items))


@router.get("/cohorts", response_model=CohortsResponse)
async def get_cohorts(
    response: Response,
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> CohortsResponse:
    add_admin_noindex_header(response)
    now_utc = datetime.now(timezone.utc)
    from_utc = now_utc - timedelta(weeks=12)

    async with SessionLocal.begin() as session:
        user_rows = (
            await session.execute(
                select(User.id, User.created_at).where(User.created_at >= from_utc)
            )
        ).all()
        purchase_rows = (
            await session.execute(
                select(Purchase.user_id, Purchase.paid_at).where(
                    Purchase.paid_at.is_not(None),
                    Purchase.status.in_(("PAID_UNCREDITED", "CREDITED")),
                )
            )
        ).all()

    user_meta: dict[int, datetime] = {int(uid): created_at for uid, created_at in user_rows}
    cohort_sizes: dict[str, int] = defaultdict(int)
    cohort_hits: dict[str, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))

    for uid, created_at in user_rows:
        week_start = (created_at - timedelta(days=created_at.weekday())).date().isoformat()
        cohort_sizes[week_start] += 1

    for uid, paid_at in purchase_rows:
        created_at = user_meta.get(int(uid))
        if created_at is None or paid_at is None or paid_at < created_at:
            continue
        week_start = (created_at - timedelta(days=created_at.weekday())).date().isoformat()
        week_offset = int((paid_at.date() - created_at.date()).days // 7)
        if week_offset < 0 or week_offset > 8:
            continue
        cohort_hits[week_start][week_offset].add(int(uid))

    offsets = list(range(0, 9))
    rows: list[dict[str, object]] = []
    for week_start in sorted(cohort_sizes.keys()):
        base = max(1, cohort_sizes[week_start])
        values = {
            f"w{offset}": round((len(cohort_hits[week_start][offset]) / base) * 100, 2)
            for offset in offsets
        }
        rows.append({"cohort_week": week_start, "users": cohort_sizes[week_start], **values})

    return CohortsResponse(week_offsets=offsets, cohorts=rows)
