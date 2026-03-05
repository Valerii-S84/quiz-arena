from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.api.routes.admin.deps import AdminPrincipal, add_admin_noindex_header, get_current_admin
from app.api.routes.admin.overview_queries import build_overview_payload
from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.services.admin.cache import get_json_cache, set_json_cache

router = APIRouter(prefix="/admin", tags=["admin-overview"])
VALID_PERIODS = {"7d": 7, "30d": 30, "90d": 90}


class KpiCard(BaseModel):
    current: float = Field(ge=0)
    previous: float = Field(ge=0)
    delta_pct: float


class OverviewResponse(BaseModel):
    period: str
    generated_at: datetime
    kpis: dict[str, KpiCard]
    revenue_series: list[dict[str, object]]
    users_series: list[dict[str, object]]
    funnel: list[dict[str, object]]
    top_products: list[dict[str, object]]
    feature_usage: dict[str, KpiCard] = Field(default_factory=dict)
    alerts: list[dict[str, object]]


@router.get("/overview", response_model=OverviewResponse)
async def get_overview(
    response: Response,
    period: str = Query(default="7d"),
    _admin: AdminPrincipal = Depends(get_current_admin),
    settings: Settings = Depends(get_settings),
) -> OverviewResponse:
    add_admin_noindex_header(response)
    days = VALID_PERIODS.get(period, 7)
    cache_key = f"admin:overview:{days}"

    cached = await get_json_cache(settings=settings, key=cache_key)
    if cached:
        return OverviewResponse.model_validate(cached)

    async with SessionLocal.begin() as session:
        payload = await build_overview_payload(
            session,
            now_utc=datetime.now(timezone.utc),
            days=days,
        )

    model = OverviewResponse.model_validate(payload)
    await set_json_cache(
        settings=settings,
        key=cache_key,
        value=jsonable_encoder(model),
        ttl_seconds=300,
    )
    return model
