from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import deps as admin_deps
from app.api.routes.admin import economy
from app.main import app


class _ScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one(self):
        return self._value


class _RowsResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, *results) -> None:
        self.results = list(results)

    async def execute(self, stmt):
        del stmt
        return self.results.pop(0)


class _AsyncBeginContext:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _session_local(*sessions: object) -> SimpleNamespace:
    remaining = list(sessions)
    return SimpleNamespace(begin=lambda: _AsyncBeginContext(remaining.pop(0)))


def _admin() -> admin_deps.AdminPrincipal:
    return admin_deps.AdminPrincipal(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
        two_factor_verified=True,
        client_ip="127.0.0.1",
    )


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides.clear()
    app.dependency_overrides[admin_deps.get_current_admin] = _admin
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_parse_datetime_handles_empty_naive_and_tz_aware_values() -> None:
    assert economy._parse_datetime(None) is None
    assert economy._parse_datetime("") is None
    assert economy._parse_datetime("2026-03-13T12:00:00") == datetime(
        2026, 3, 13, 12, 0, tzinfo=UTC
    )
    assert economy._parse_datetime("2026-03-13T13:00:00+01:00") == datetime(
        2026,
        3,
        13,
        12,
        0,
        tzinfo=UTC,
    )


def test_admin_economy_purchases_route_builds_items_and_charts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    purchase_a = SimpleNamespace(
        id=uuid4(),
        user_id=7,
        product_code="ENERGY_10",
        stars_amount=5,
        paid_at=datetime(2026, 3, 13, 10, 0, tzinfo=UTC),
        created_at=datetime(2026, 3, 13, 9, 0, tzinfo=UTC),
        raw_successful_payment={"source": "offer", "utm": {"campaign": "spring"}},
        status="CREDITED",
    )
    purchase_b = SimpleNamespace(
        id=uuid4(),
        user_id=8,
        product_code="PREMIUM_MONTH",
        stars_amount=99,
        paid_at=datetime(2026, 3, 13, 8, 0, tzinfo=UTC),
        created_at=datetime(2026, 3, 13, 7, 0, tzinfo=UTC),
        raw_successful_payment=None,
        status="PAID_UNCREDITED",
    )
    monkeypatch.setattr(
        economy,
        "SessionLocal",
        _session_local(
            _Session(
                _ScalarResult(2),
                _RowsResult([(purchase_a, "alice"), (purchase_b, None)]),
                _RowsResult([("PREMIUM_MONTH", 99), ("ENERGY_10", 5)]),
            )
        ),
    )

    async def _fake_build_ltv_30d_by_cohort(session, *, cohort_from_utc, cohort_to_utc):
        assert cohort_from_utc == datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
        assert cohort_to_utc == datetime(2026, 3, 20, 0, 0, tzinfo=UTC)
        return [{"cohort_week": "2026-03-03", "w0": 100.0}]

    monkeypatch.setattr(economy, "build_ltv_30d_by_cohort", _fake_build_ltv_30d_by_cohort)

    response = client.get(
        "/admin/economy/purchases",
        params={
            "page": 1,
            "limit": 2,
            "from": "2026-03-01T00:00:00Z",
            "to": "2026-03-20T00:00:00Z",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    payload = response.json()
    assert payload["total"] == 2
    assert payload["page"] == 1
    assert payload["pages"] == 1
    assert payload["items"][0]["username"] == "alice"
    assert payload["items"][0]["source"] == "offer"
    assert payload["items"][0]["utm"] == {"campaign": "spring"}
    assert payload["items"][1]["source"] == "telegram"
    assert payload["items"][1]["utm"] is None
    assert payload["charts"]["revenue_by_product"] == [
        {"product": "PREMIUM_MONTH", "stars": 99, "eur": 1.98},
        {"product": "ENERGY_10", "stars": 5, "eur": 0.1},
    ]
    assert payload["charts"]["ltv_30d_by_cohort"] == [{"cohort_week": "2026-03-03", "w0": 100.0}]


def test_admin_economy_subscriptions_route_serializes_active_entitlements(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    entitlement = SimpleNamespace(
        id=12,
        user_id=5,
        status="ACTIVE",
        starts_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        ends_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
    )
    monkeypatch.setattr(
        economy,
        "SessionLocal",
        _session_local(_Session(_RowsResult([(entitlement, "alice")]))),
    )

    response = client.get("/admin/economy/subscriptions")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "items": [
            {
                "id": 12,
                "user_id": 5,
                "username": "alice",
                "status": "ACTIVE",
                "starts_at": "2026-03-01T12:00:00+00:00",
                "ends_at": "2026-04-01T12:00:00+00:00",
            }
        ],
        "total": 1,
    }


def test_admin_economy_cohorts_route_groups_users_and_filters_invalid_purchases(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_rows = [
        (1, datetime(2026, 1, 5, 12, 0, tzinfo=UTC)),
        (2, datetime(2026, 1, 6, 9, 0, tzinfo=UTC)),
    ]
    purchase_rows = [
        (1, datetime(2026, 1, 12, 12, 0, tzinfo=UTC)),
        (1, datetime(2026, 1, 20, 12, 0, tzinfo=UTC)),
        (2, datetime(2026, 1, 4, 12, 0, tzinfo=UTC)),
        (2, datetime(2026, 3, 20, 12, 0, tzinfo=UTC)),
    ]
    monkeypatch.setattr(
        economy,
        "SessionLocal",
        _session_local(_Session(_RowsResult(user_rows), _RowsResult(purchase_rows))),
    )

    response = client.get("/admin/economy/cohorts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["week_offsets"] == list(range(9))
    assert payload["cohorts"] == [
        {
            "cohort_week": "2026-01-05",
            "users": 2,
            "w0": 0.0,
            "w1": 50.0,
            "w2": 50.0,
            "w3": 0.0,
            "w4": 0.0,
            "w5": 0.0,
            "w6": 0.0,
            "w7": 0.0,
            "w8": 0.0,
        }
    ]
