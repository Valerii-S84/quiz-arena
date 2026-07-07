from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from typing import cast

import pytest
from fastapi.testclient import TestClient

from app.api.routes import public_website_analytics as website_routes
from app.db.models.website_events import WebsiteEvent
from app.main import app
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


class _RouteClock:
    def __init__(self, now_utc: datetime) -> None:
        self._now_utc = now_utc

    def now(self, tz: tzinfo | None = None) -> datetime:
        if tz is None:
            return self._now_utc
        return self._now_utc.astimezone(tz)


def _settings():
    return build_settings(
        website_analytics_visitor_salt="website-test-salt",
        website_analytics_rate_limit_per_minute=100,
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
    monkeypatch.setattr(
        website_routes,
        "datetime",
        _RouteClock(datetime(2026, 6, 4, 10, 31, tzinfo=timezone.utc)),
    )
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
