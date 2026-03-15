from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from typing import cast

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.sql.elements import ColumnElement

from app.api.routes.admin.deps import AdminPrincipal, add_admin_noindex_header, get_current_admin
from app.db.models.purchases import Purchase

from .models import CohortsResponse, PurchasesResponse, SubscriptionsResponse
from .queries import fetch_cohort_rows, fetch_purchase_rows, fetch_subscription_rows
from .serializers import (
    build_cohorts_response,
    build_purchases_response,
    build_subscriptions_response,
)

router = APIRouter(prefix="/admin/economy", tags=["admin-economy"])


def _economy_module() -> ModuleType:
    return cast(ModuleType, sys.modules[__package__])


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
    module = _economy_module()
    now_utc = datetime.now(timezone.utc)
    from_dt = module._parse_datetime(from_)
    to_dt = module._parse_datetime(to)

    filters: list[ColumnElement[bool]] = [Purchase.paid_at.is_not(None)]
    if product:
        filters.append(Purchase.product_code == product)
    if user_id is not None:
        filters.append(Purchase.user_id == user_id)
    if from_dt is not None:
        filters.append(Purchase.paid_at >= from_dt)
    if to_dt is not None:
        filters.append(Purchase.paid_at < to_dt)

    async with module.SessionLocal.begin() as session:
        rows = await fetch_purchase_rows(session, filters=filters, page=page, limit=limit)
        ltv_30d_by_cohort = await module.build_ltv_30d_by_cohort(
            session,
            cohort_from_utc=from_dt or (now_utc - timedelta(weeks=12)),
            cohort_to_utc=to_dt or now_utc,
        )

    return build_purchases_response(
        rows=rows,
        page=page,
        limit=limit,
        ltv_30d_by_cohort=ltv_30d_by_cohort,
    )


@router.get("/subscriptions", response_model=SubscriptionsResponse)
async def list_subscriptions(
    response: Response,
    status: str = Query(default="ACTIVE"),
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> SubscriptionsResponse:
    add_admin_noindex_header(response)
    module = _economy_module()
    async with module.SessionLocal.begin() as session:
        rows = await fetch_subscription_rows(session, status=status)
    return build_subscriptions_response(rows)


@router.get("/cohorts", response_model=CohortsResponse)
async def get_cohorts(
    response: Response,
    _admin: AdminPrincipal = Depends(get_current_admin),
) -> CohortsResponse:
    add_admin_noindex_header(response)
    module = _economy_module()
    now_utc = datetime.now(timezone.utc)
    from_utc = now_utc - timedelta(weeks=12)

    async with module.SessionLocal.begin() as session:
        rows = await fetch_cohort_rows(session, from_utc=from_utc)

    return build_cohorts_response(rows)
