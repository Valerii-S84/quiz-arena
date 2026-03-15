from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from app.api.routes.admin.pagination import build_pagination
from app.db.models.entitlements import Entitlement
from app.db.models.purchases import Purchase

from .helpers import STAR_TO_EUR_RATE
from .models import CohortsResponse, PurchasesResponse, SubscriptionsResponse
from .queries import CohortQueryRows, PurchasesQueryRows


def build_purchases_response(
    *,
    rows: PurchasesQueryRows,
    page: int,
    limit: int,
    ltv_30d_by_cohort: list[dict[str, object]],
) -> PurchasesResponse:
    items: list[dict[str, object]] = []
    for purchase, username in rows.purchase_rows:
        source = "telegram"
        utm = None
        if isinstance(purchase.raw_successful_payment, dict):
            source = str(purchase.raw_successful_payment.get("source") or source)
            utm = purchase.raw_successful_payment.get("utm")
        items.append(
            _serialize_purchase_item(
                purchase=purchase,
                username=username,
                source=source,
                utm=utm,
            )
        )

    pagination = build_pagination(total=rows.total, page=page, limit=limit)
    return PurchasesResponse(
        items=items,
        total=pagination["total"],
        page=pagination["page"],
        pages=pagination["pages"],
        charts={
            "revenue_by_product": [
                {
                    "product": product_code,
                    "stars": total_stars,
                    "eur": float(Decimal(total_stars) * STAR_TO_EUR_RATE),
                }
                for product_code, total_stars in rows.revenue_by_product_rows
            ],
            "ltv_30d_by_cohort": ltv_30d_by_cohort,
        },
    )


def _serialize_purchase_item(
    *,
    purchase: Purchase,
    username: str | None,
    source: str,
    utm: object,
) -> dict[str, object]:
    return {
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


def build_subscriptions_response(
    rows: list[tuple[Entitlement, str | None]],
) -> SubscriptionsResponse:
    items: list[dict[str, object]] = [
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


def build_cohorts_response(rows: CohortQueryRows) -> CohortsResponse:
    user_meta: dict[int, datetime] = {uid: created_at for uid, created_at in rows.user_rows}
    cohort_sizes: dict[str, int] = defaultdict(int)
    cohort_hits: dict[str, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))

    for uid, created_at in rows.user_rows:
        week_start = (created_at - timedelta(days=created_at.weekday())).date().isoformat()
        cohort_sizes[week_start] += 1

    for uid, paid_at in rows.purchase_rows:
        cohort_created_at = user_meta.get(uid)
        if cohort_created_at is None or paid_at is None or paid_at < cohort_created_at:
            continue
        assert paid_at is not None
        paid_at_utc = paid_at
        week_start = (
            (cohort_created_at - timedelta(days=cohort_created_at.weekday())).date().isoformat()
        )
        week_offset = int((paid_at_utc.date() - cohort_created_at.date()).days // 7)
        if week_offset < 0 or week_offset > 8:
            continue
        cohort_hits[week_start][week_offset].add(uid)

    offsets = list(range(0, 9))
    cohorts: list[dict[str, object]] = []
    for week_start in sorted(cohort_sizes.keys()):
        base = max(1, cohort_sizes[week_start])
        values = {
            f"w{offset}": round((len(cohort_hits[week_start][offset]) / base) * 100, 2)
            for offset in offsets
        }
        cohorts.append({"cohort_week": week_start, "users": cohort_sizes[week_start], **values})

    return CohortsResponse(week_offsets=offsets, cohorts=cohorts)
