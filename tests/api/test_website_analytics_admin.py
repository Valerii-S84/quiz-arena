from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import deps as admin_deps
from app.api.routes.admin import website_analytics as admin_website_routes
from app.api.routes.website_analytics_models import (
    WebsiteAnalyticsOverviewResponse,
    WebsiteAnalyticsTotals,
)
from app.main import app
from app.services import website_analytics_overview


class _SessionContextStub:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _Result:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def one(self) -> object:
        return self._rows[0]

    def all(self) -> list[object]:
        return list(self._rows)


class _OverviewSession:
    def __init__(self) -> None:
        self._results = [
            _Result(
                [
                    SimpleNamespace(
                        page_views_total=3,
                        unique_visitors_total=2,
                        telegram_cta_clicks_total=1,
                    )
                ]
            ),
            _Result(
                [
                    SimpleNamespace(
                        date=datetime(2026, 6, 2, tzinfo=timezone.utc).date(),
                        unique_visitors=1,
                        page_views=1,
                        telegram_cta_clicks=0,
                    ),
                    SimpleNamespace(
                        date=datetime(2026, 6, 4, tzinfo=timezone.utc).date(),
                        unique_visitors=2,
                        page_views=2,
                        telegram_cta_clicks=1,
                    ),
                ]
            ),
            _Result(
                [
                    SimpleNamespace(
                        path="/",
                        page_views=2,
                        unique_visitors=2,
                        telegram_cta_clicks=1,
                    )
                ]
            ),
        ]

    async def execute(self, statement: object) -> _Result:
        del statement
        return self._results.pop(0)


def _admin() -> admin_deps.AdminPrincipal:
    return admin_deps.AdminPrincipal(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
        two_factor_verified=True,
        client_ip="127.0.0.1",
    )


@pytest.fixture(autouse=True)
def _clear_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_website_analytics_overview_fills_daily_series(monkeypatch) -> None:
    monkeypatch.setattr(
        website_analytics_overview,
        "SessionLocal",
        SimpleNamespace(begin=lambda: _SessionContextStub(_OverviewSession())),
    )

    payload = await website_analytics_overview.build_website_analytics_overview(
        days=3,
        now_utc=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
    )

    assert payload.totals.page_views_total == 3
    assert payload.totals.unique_visitors_total == 2
    assert payload.totals.telegram_cta_clicks_total == 1
    assert [point.date.isoformat() for point in payload.daily_series] == [
        "2026-06-02",
        "2026-06-03",
        "2026-06-04",
    ]
    assert payload.daily_series[1].page_views == 0
    assert payload.daily_series[2].unique_visitors == 2
    assert payload.top_pages[0].path == "/"
    assert payload.top_pages[0].telegram_cta_clicks == 1


def test_admin_website_analytics_requires_admin_session() -> None:
    client = TestClient(app)

    response = client.get("/admin/website-analytics/overview?days=7")

    assert response.status_code == 401


def test_admin_website_analytics_route_returns_overview(monkeypatch) -> None:
    app.dependency_overrides[admin_deps.get_current_admin] = _admin
    client = TestClient(app)

    async def _overview(**kwargs):
        del kwargs
        return WebsiteAnalyticsOverviewResponse(
            generated_at=datetime(2026, 6, 4, 12, 0, tzinfo=timezone.utc),
            days=7,
            totals=WebsiteAnalyticsTotals(
                page_views_total=10,
                unique_visitors_total=4,
                telegram_cta_clicks_total=2,
            ),
            daily_series=[],
            top_pages=[],
        )

    monkeypatch.setattr(admin_website_routes, "build_website_analytics_overview", _overview)

    response = client.get("/admin/website-analytics/overview?days=7")

    assert response.status_code == 200
    assert response.json()["totals"] == {
        "page_views_total": 10,
        "unique_visitors_total": 4,
        "telegram_cta_clicks_total": 2,
    }
