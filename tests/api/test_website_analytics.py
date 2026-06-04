from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes import public_website_analytics as website_routes
from app.api.routes.admin import deps as admin_deps
from app.api.routes.admin import website_analytics as admin_website_routes
from app.api.routes.website_analytics_models import (
    WebsiteAnalyticsOverviewResponse,
    WebsiteAnalyticsTotals,
)
from app.db.models.website_events import WebsiteEvent
from app.main import app
from app.services import website_analytics_overview
from tests.type_helpers import build_settings


class _SessionLocalStub:
    def __init__(self) -> None:
        self.added_rows: list[object] = []

    def begin(self):
        return _SessionContextStub(self)

    def add(self, item: object) -> None:
        self.added_rows.append(item)


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


def _settings():
    return build_settings(
        website_analytics_visitor_salt="website-test-salt",
        website_analytics_rate_limit_per_minute=100,
    )


def _admin() -> admin_deps.AdminPrincipal:
    return admin_deps.AdminPrincipal(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
        two_factor_verified=True,
        client_ip="127.0.0.1",
    )


async def _not_limited(*args, **kwargs) -> bool:
    del args, kwargs
    return False


@pytest.fixture(autouse=True)
def _clear_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


def test_public_website_analytics_ingest_accepts_valid_event(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(website_routes, "SessionLocal", session_stub)
    monkeypatch.setattr(website_routes, "is_website_analytics_rate_limited", _not_limited)
    app.dependency_overrides[website_routes.get_settings] = _settings
    client = TestClient(app)

    response = client.post(
        "/api/public/website-analytics/events",
        json={
            "event_type": "telegram_cta_click",
            "visitor_id": "visitor-abc-123456",
            "path": "/?utm_source=newsletter",
            "referrer": "example.com/start",
            "utm_source": "newsletter",
            "utm_medium": "email",
            "utm_campaign": "june",
            "timestamp": "2026-06-04T10:30:00+00:00",
            "metadata": {"public_event_name": "hero_cta_click", "cta": "telegram_bot"},
        },
    )

    assert response.status_code == 204
    assert response.content == b""
    assert len(session_stub.added_rows) == 1
    stored = cast(WebsiteEvent, session_stub.added_rows[0])
    assert stored.event_type == "telegram_cta_click"
    assert stored.path == "/"
    assert stored.referrer == "example.com/start"
    assert stored.utm_source == "newsletter"
    assert stored.local_date_berlin.isoformat() == "2026-06-04"
    assert stored.visitor_hash != "visitor-abc-123456"
    assert len(stored.visitor_hash) == 64
    assert stored.event_metadata == {
        "public_event_name": "hero_cta_click",
        "cta": "telegram_bot",
    }


def test_public_website_analytics_invalid_event_type_is_rejected(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(website_routes, "SessionLocal", session_stub)
    monkeypatch.setattr(website_routes, "is_website_analytics_rate_limited", _not_limited)
    app.dependency_overrides[website_routes.get_settings] = _settings
    client = TestClient(app)

    response = client.post(
        "/api/public/website-analytics/events",
        json={
            "event_type": "signup",
            "visitor_id": "visitor-abc-123456",
            "path": "/",
        },
    )

    assert response.status_code == 422
    assert not session_stub.added_rows


def test_public_website_analytics_invalid_path_is_silently_ignored(monkeypatch) -> None:
    session_stub = _SessionLocalStub()
    monkeypatch.setattr(website_routes, "SessionLocal", session_stub)
    monkeypatch.setattr(website_routes, "is_website_analytics_rate_limited", _not_limited)
    app.dependency_overrides[website_routes.get_settings] = _settings
    client = TestClient(app)

    response = client.post(
        "/api/public/website-analytics/events",
        json={
            "event_type": "page_view",
            "visitor_id": "visitor-abc-123456",
            "path": "https://example.com/leak",
        },
    )

    assert response.status_code == 204
    assert not session_stub.added_rows


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
