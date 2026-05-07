from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.routes.admin import deps as admin_deps
from app.api.routes.admin import promo
from app.main import app

NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def _admin() -> admin_deps.AdminPrincipal:
    return admin_deps.AdminPrincipal(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
        two_factor_verified=True,
        client_ip="127.0.0.1",
    )


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    app.dependency_overrides.clear()
    app.dependency_overrides[admin_deps.get_current_admin] = _admin
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_admin_promo_create_and_bulk_routes_delegate_to_handlers(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str | int]] = []

    async def _create(*, payload, admin):
        assert payload.code == "SPRING50"
        assert admin.email == "admin@example.com"
        calls.append(("create", payload.code))
        return {"id": 1, "raw_code": "SPRING50"}

    async def _bulk(*, payload, admin):
        assert payload.count == 2
        assert admin.email == "admin@example.com"
        calls.append(("bulk", payload.count))
        return {"generated": 2, "count": 2, "codes": ["MASS1", "MASS2"], "items": []}

    monkeypatch.setattr(promo, "_create_promo", _create)
    monkeypatch.setattr(promo, "_create_bulk_promos", _bulk)

    created = client.post(
        "/admin/promo",
        json={
            "code": "SPRING50",
            "campaign_name": "Fruehling",
            "discount_type": "PERCENT",
            "discount_value": 50,
            "valid_from": NOW.isoformat(),
            "valid_until": (NOW + timedelta(days=1)).isoformat(),
        },
    )
    bulk = client.post(
        "/admin/promo/bulk",
        json={
            "count": 2,
            "prefix": "mass",
            "discount_type": "FREE",
            "valid_from": NOW.isoformat(),
            "valid_until": (NOW + timedelta(days=1)).isoformat(),
        },
    )
    bulk_generate = client.post(
        "/admin/promo/bulk-generate",
        json={
            "count": 2,
            "prefix": "mass",
            "discount_type": "FREE",
            "valid_from": NOW.isoformat(),
            "valid_until": (NOW + timedelta(days=1)).isoformat(),
        },
    )

    assert created.status_code == 200
    assert bulk.status_code == 200
    assert bulk_generate.status_code == 200
    assert created.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert bulk.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert bulk_generate.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert calls == [("create", "SPRING50"), ("bulk", 2), ("bulk", 2)]


def test_admin_promo_create_route_rejects_invalid_discount_type_and_dates(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected(**kwargs):
        raise AssertionError("handler should not run for invalid payload")

    monkeypatch.setattr(promo, "_create_promo", _unexpected)

    invalid_discount = client.post(
        "/admin/promo",
        json={
            "code": "SPRING50",
            "discount_type": "MONEY",
            "discount_value": 50,
        },
    )
    invalid_dates = client.post(
        "/admin/promo",
        json={
            "code": "SPRING50",
            "discount_type": "PERCENT",
            "discount_value": 50,
            "valid_from": NOW.isoformat(),
            "valid_until": (NOW - timedelta(minutes=1)).isoformat(),
        },
    )
    mixed_timezone_awareness = client.post(
        "/admin/promo",
        json={
            "code": "SPRING50",
            "discount_type": "PERCENT",
            "discount_value": 50,
            "valid_from": NOW.isoformat(),
            "valid_until": "2026-03-16T12:00:00",
        },
    )

    assert invalid_discount.status_code == 422
    assert invalid_dates.status_code == 422
    assert mixed_timezone_awareness.status_code == 422


def test_admin_promo_mutation_routes_delegate_with_ids(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []

    async def _patch(*, promo_id, payload, admin):
        assert payload.max_uses == 0
        assert admin.email == "admin@example.com"
        calls.append(("patch", promo_id))
        return {"id": promo_id, "status": "active"}

    async def _toggle(*, promo_id, admin):
        assert admin.email == "admin@example.com"
        calls.append(("toggle", promo_id))
        return {"id": promo_id, "status": "inactive"}

    async def _revoke(*, promo_id, payload, admin):
        assert payload is not None
        assert payload.reason == "Misuse"
        assert admin.email == "admin@example.com"
        calls.append(("revoke", promo_id))
        return {"promo": {"id": promo_id}, "revoked_count": 1, "reason": "Misuse"}

    monkeypatch.setattr(promo, "_patch_promo", _patch)
    monkeypatch.setattr(promo, "_toggle_promo", _toggle)
    monkeypatch.setattr(promo, "_revoke_promo", _revoke)

    patched = client.request(
        "PATCH",
        "/admin/promo/42",
        json={"type": "discount_percent", "value": 25, "max_uses": 0},
    )
    toggled = client.request("PATCH", "/admin/promo/42/toggle")
    revoked = client.post("/admin/promo/42/revoke", json={"reason": "Misuse"})

    assert patched.status_code == 200
    assert toggled.status_code == 200
    assert revoked.status_code == 200
    assert calls == [("patch", 42), ("toggle", 42), ("revoke", 42)]


def test_admin_promo_read_routes_delegate_query_and_reveal_flags(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    async def _list(*, status, query, page, limit):
        calls.append(("list", (status, query, page, limit)))
        return {"items": [], "total": 0, "page": page, "pages": 0}

    async def _products():
        calls.append(("products", None))
        return {"items": ["ENERGY_10"]}

    async def _check(*, code):
        calls.append(("check", code))
        return {"normalized_code": code.upper(), "exists": False}

    async def _detail(*, promo_id, admin, reveal):
        assert admin.email == "admin@example.com"
        calls.append(("detail", (promo_id, reveal)))
        return {"id": promo_id, "raw_code": None, "can_reveal_code": False}

    async def _stats(*, promo_id):
        calls.append(("stats", promo_id))
        return {"used_total": 0, "reserved_active": 0, "status_totals": {}, "redemptions": []}

    async def _audit(*, promo_id, limit):
        calls.append(("audit", (promo_id, limit)))
        return {"items": []}

    async def _usages(*, promo_id, page, limit):
        calls.append(("usages", (promo_id, page, limit)))
        return {"items": [], "total": 0, "page": page, "pages": 0}

    async def _export():
        calls.append(("export", None))
        return {"ok": True}

    monkeypatch.setattr(promo, "_list_promos", _list)
    monkeypatch.setattr(promo, "_list_promo_products", _products)
    monkeypatch.setattr(promo, "_check_promo_code", _check)
    monkeypatch.setattr(promo, "_get_promo", _detail)
    monkeypatch.setattr(promo, "_get_promo_stats", _stats)
    monkeypatch.setattr(promo, "_list_promo_audit", _audit)
    monkeypatch.setattr(promo, "_list_promo_usages", _usages)
    monkeypatch.setattr(promo, "_export_promos", _export)

    listed = client.get("/admin/promo?status=active&query=spring&page=2&limit=20")
    products = client.get("/admin/promo/products")
    checked = client.get("/admin/promo/check-code?code=spring50")
    exported = client.get("/admin/promo/export?format=csv")
    detail = client.get("/admin/promo/42?reveal=true")
    stats = client.get("/admin/promo/42/stats")
    audit = client.get("/admin/promo/42/audit?limit=10")
    usages = client.get("/admin/promo/42/usages?page=3&limit=5")
    unsupported_export = client.get("/admin/promo/export?format=json")

    assert listed.status_code == 200
    assert products.status_code == 200
    assert checked.status_code == 200
    assert exported.status_code == 200
    assert detail.status_code == 200
    assert stats.status_code == 200
    assert audit.status_code == 200
    assert usages.status_code == 200
    assert unsupported_export.status_code == 400
    assert calls == [
        ("list", ("active", "spring", 2, 20)),
        ("products", None),
        ("check", "spring50"),
        ("export", None),
        ("detail", (42, True)),
        ("stats", 42),
        ("audit", (42, 10)),
        ("usages", (42, 3, 5)),
    ]
