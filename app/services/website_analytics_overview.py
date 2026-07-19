from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import distinct, func, select

from app.api.routes.website_analytics_models import (
    WebsiteAnalyticsDailyPoint,
    WebsiteAnalyticsOverviewResponse,
    WebsiteAnalyticsTopPage,
    WebsiteAnalyticsTotals,
)
from app.db.models.website_events import WebsiteEvent
from app.db.session import SessionLocal
from app.economy.energy.constants import BERLIN_TIMEZONE

PAGE_VIEW_EVENT = "page_view"
TELEGRAM_CTA_CLICK_EVENT = "telegram_cta_click"


def _row_value(row: object, key: str, default: object = 0) -> object:
    if isinstance(row, Mapping):
        return row.get(key, default)
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return mapping.get(key, default)
    return getattr(row, key, default)


def _as_int(value: object) -> int:
    if value is None:
        return 0
    return int(cast(Any, value))


def _build_daily_series(
    *,
    start_date: date,
    days: int,
    rows: Sequence[object],
) -> list[WebsiteAnalyticsDailyPoint]:
    rows_by_date = {_row_value(row, "date"): row for row in rows}
    series: list[WebsiteAnalyticsDailyPoint] = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        row = rows_by_date.get(day)
        series.append(
            WebsiteAnalyticsDailyPoint(
                date=day,
                unique_visitors=_as_int(_row_value(row, "unique_visitors")) if row else 0,
                page_views=_as_int(_row_value(row, "page_views")) if row else 0,
                telegram_cta_clicks=_as_int(_row_value(row, "telegram_cta_clicks")) if row else 0,
            )
        )
    return series


def _build_top_pages(rows: Sequence[object]) -> list[WebsiteAnalyticsTopPage]:
    return [
        WebsiteAnalyticsTopPage(
            path=str(_row_value(row, "path", "/")),
            page_views=_as_int(_row_value(row, "page_views")),
            unique_visitors=_as_int(_row_value(row, "unique_visitors")),
            telegram_cta_clicks=_as_int(_row_value(row, "telegram_cta_clicks")),
        )
        for row in rows
    ]


async def _fetch_totals(session: Any, start_date: date, end_date: date) -> object:
    result = await session.execute(
        select(
            func.count()
            .filter(WebsiteEvent.event_type == PAGE_VIEW_EVENT)
            .label("page_views_total"),
            func.count(distinct(WebsiteEvent.visitor_hash)).label("unique_visitors_total"),
            func.count()
            .filter(WebsiteEvent.event_type == TELEGRAM_CTA_CLICK_EVENT)
            .label("telegram_cta_clicks_total"),
        ).where(
            WebsiteEvent.local_date_berlin >= start_date,
            WebsiteEvent.local_date_berlin <= end_date,
        )
    )
    return result.one()


async def _fetch_daily_rows(session: Any, start_date: date, end_date: date) -> Sequence[object]:
    result = await session.execute(
        select(
            WebsiteEvent.local_date_berlin.label("date"),
            func.count(distinct(WebsiteEvent.visitor_hash)).label("unique_visitors"),
            func.count().filter(WebsiteEvent.event_type == PAGE_VIEW_EVENT).label("page_views"),
            func.count()
            .filter(WebsiteEvent.event_type == TELEGRAM_CTA_CLICK_EVENT)
            .label("telegram_cta_clicks"),
        )
        .where(
            WebsiteEvent.local_date_berlin >= start_date,
            WebsiteEvent.local_date_berlin <= end_date,
        )
        .group_by(WebsiteEvent.local_date_berlin)
        .order_by(WebsiteEvent.local_date_berlin.asc())
    )
    return list(result.all())


async def _fetch_top_page_rows(
    session: Any,
    start_date: date,
    end_date: date,
) -> Sequence[object]:
    page_view_count = func.count().filter(WebsiteEvent.event_type == PAGE_VIEW_EVENT)
    result = await session.execute(
        select(
            WebsiteEvent.path.label("path"),
            page_view_count.label("page_views"),
            func.count(distinct(WebsiteEvent.visitor_hash)).label("unique_visitors"),
            func.count()
            .filter(WebsiteEvent.event_type == TELEGRAM_CTA_CLICK_EVENT)
            .label("telegram_cta_clicks"),
        )
        .where(
            WebsiteEvent.local_date_berlin >= start_date,
            WebsiteEvent.local_date_berlin <= end_date,
        )
        .group_by(WebsiteEvent.path)
        .order_by(page_view_count.desc(), WebsiteEvent.path.asc())
        .limit(10)
    )
    return list(result.all())


async def build_website_analytics_overview(
    *,
    days: int,
    now_utc: datetime,
) -> WebsiteAnalyticsOverviewResponse:
    berlin_today = now_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()
    start_date = berlin_today - timedelta(days=days - 1)

    async with SessionLocal.begin() as session:
        totals_row = await _fetch_totals(session, start_date, berlin_today)
        daily_rows = await _fetch_daily_rows(session, start_date, berlin_today)
        top_page_rows = await _fetch_top_page_rows(session, start_date, berlin_today)

    return WebsiteAnalyticsOverviewResponse(
        generated_at=now_utc,
        days=days,
        totals=WebsiteAnalyticsTotals(
            page_views_total=_as_int(_row_value(totals_row, "page_views_total")),
            unique_visitors_total=_as_int(_row_value(totals_row, "unique_visitors_total")),
            telegram_cta_clicks_total=_as_int(_row_value(totals_row, "telegram_cta_clicks_total")),
        ),
        daily_series=_build_daily_series(start_date=start_date, days=days, rows=daily_rows),
        top_pages=_build_top_pages(top_page_rows),
    )
