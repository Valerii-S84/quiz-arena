from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.admin import deps as admin_deps
from app.api.routes.admin import promo_read_catalog, promo_reads
from tests.type_helpers import AsyncBeginContext, build_promo_code, build_promo_redemption

NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def _session_local(*sessions: object) -> SimpleNamespace:
    remaining = list(sessions)
    return SimpleNamespace(begin=lambda: AsyncBeginContext(remaining.pop(0)))


def _promo(**overrides: object):
    payload = {
        "id": 11,
        "code_prefix": "SPRING",
        "campaign_name": "Spring sale",
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=365),
        "created_at": NOW - timedelta(days=2),
        "updated_at": NOW - timedelta(hours=1),
    }
    payload.update(overrides)
    return build_promo_code(**payload)


async def _streaming_text(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(str(chunk))
    return "".join(chunks)


@pytest.mark.asyncio
async def test_list_promos_serializes_items_and_validates_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    promo = _promo()

    async def _list_codes(session_obj, **kwargs):
        assert session_obj is session
        assert kwargs["status"] == "active"
        assert kwargs["query"] == "spring"
        assert kwargs["page"] == 2
        assert kwargs["limit"] == 1
        return [promo]

    async def _count_codes(session_obj, **kwargs):
        assert session_obj is session
        assert kwargs["status"] == "active"
        assert kwargs["query"] == "spring"
        return 3

    monkeypatch.setattr(promo_reads, "SessionLocal", _session_local(session))
    monkeypatch.setattr(promo_reads.AdminRuntimePromoRepo, "list_codes", _list_codes)
    monkeypatch.setattr(promo_reads.AdminRuntimePromoRepo, "count_codes", _count_codes)

    payload = await promo_reads.list_promos(status="active", query="spring", page=2, limit=1)
    items = cast(list[dict[str, object]], payload["items"])

    assert payload["total"] == 3
    assert payload["page"] == 2
    assert payload["pages"] == 3
    assert items[0]["code"] == "SPRING****"

    with pytest.raises(HTTPException) as exc_info:
        await promo_reads.list_promos(status="broken", query=None, page=1, limit=10)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == {"code": "E_PROMO_STATUS_INVALID"}


@pytest.mark.asyncio
async def test_get_promo_surfaces_decrypt_failure_as_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    promo = _promo(code_encrypted=b"ciphertext")

    async def _get_by_id(session_obj, promo_id: int):
        assert session_obj is session
        assert promo_id == promo.id
        return promo

    monkeypatch.setattr(promo_reads, "SessionLocal", _session_local(session))
    monkeypatch.setattr(promo_reads.AdminRuntimePromoRepo, "get_by_id", _get_by_id)
    monkeypatch.setattr(
        promo_reads,
        "decrypt_promo_code",
        lambda ciphertext: (_ for _ in ()).throw(ValueError("boom")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await promo_reads.get_promo(
            promo_id=promo.id,
            admin=admin_deps.AdminPrincipal(
                id=uuid4(),
                email="admin@example.com",
                role="super_admin",
                two_factor_verified=True,
                client_ip="127.0.0.1",
            ),
            reveal=True,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {"code": "E_PROMO_DECRYPT_FAILED"}


@pytest.mark.asyncio
async def test_get_promo_stats_and_usages_serialize_runtime_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    promo = _promo(used_total=2)
    reserved = build_promo_redemption(
        promo_code_id=promo.id,
        user_id=21,
        status="RESERVED",
        created_at=NOW - timedelta(minutes=20),
        updated_at=NOW - timedelta(minutes=10),
        applied_at=None,
    )
    applied = build_promo_redemption(
        promo_code_id=promo.id,
        user_id=22,
        status="APPLIED",
        created_at=NOW - timedelta(hours=1),
        updated_at=NOW - timedelta(minutes=55),
        applied_at=NOW - timedelta(minutes=50),
    )

    async def _get_by_id(session_obj, promo_id: int):
        assert session_obj is session
        assert promo_id == promo.id
        return promo

    async def _count_reserved(session_obj, **kwargs):
        assert session_obj is session
        assert kwargs["promo_id"] == promo.id
        return 1

    async def _count_by_status(session_obj, **kwargs):
        assert session_obj is session
        assert kwargs["promo_id"] == promo.id
        return {"RESERVED": 1, "APPLIED": 1}

    async def _recent(session_obj, promo_id: int):
        assert session_obj is session
        assert promo_id == promo.id
        return [(reserved, None), (applied, "ENERGY_10")]

    async def _list_redemptions(session_obj, **kwargs):
        assert session_obj is session
        assert kwargs == {"promo_id": promo.id, "page": 1, "limit": 2}
        return [reserved, applied]

    async def _count_redemptions(session_obj, **kwargs):
        assert session_obj is session
        assert kwargs == {"promo_id": promo.id}
        return 2

    monkeypatch.setattr(promo_reads, "SessionLocal", _session_local(session, session))
    monkeypatch.setattr(promo_reads.AdminRuntimePromoRepo, "get_by_id", _get_by_id)
    monkeypatch.setattr(
        promo_reads.AdminRuntimePromoRepo,
        "count_active_reserved_redemptions",
        _count_reserved,
    )
    monkeypatch.setattr(
        promo_reads.AdminRuntimePromoRepo,
        "count_redemptions_by_status",
        _count_by_status,
    )
    monkeypatch.setattr(promo_reads.AdminRuntimePromoRepo, "list_recent_redemptions", _recent)
    monkeypatch.setattr(promo_reads.AdminRuntimePromoRepo, "list_redemptions", _list_redemptions)
    monkeypatch.setattr(
        promo_reads.AdminRuntimePromoRepo,
        "count_redemptions",
        _count_redemptions,
    )

    stats = await promo_reads.get_promo_stats(promo_id=promo.id)
    usages = await promo_reads.list_promo_usages(promo_id=promo.id, page=1, limit=2)

    assert stats == {
        "used_total": 2,
        "reserved_active": 1,
        "status_totals": {"RESERVED": 1, "APPLIED": 1},
        "redemptions": [
            {
                "user_id": 21,
                "redeemed_at": (NOW - timedelta(minutes=10)).isoformat(),
                "status": "RESERVED",
                "product_id": None,
            },
            {
                "user_id": 22,
                "redeemed_at": (NOW - timedelta(minutes=50)).isoformat(),
                "status": "APPLIED",
                "product_id": "ENERGY_10",
            },
        ],
    }
    assert usages == {
        "items": [
            {
                "id": str(reserved.id),
                "user_id": 21,
                "status": "RESERVED",
                "used_at": (NOW - timedelta(minutes=10)).isoformat(),
            },
            {
                "id": str(applied.id),
                "user_id": 22,
                "status": "APPLIED",
                "used_at": (NOW - timedelta(minutes=50)).isoformat(),
            },
        ],
        "total": 2,
        "page": 1,
        "pages": 1,
    }


@pytest.mark.asyncio
async def test_list_promo_audit_and_check_code_cover_found_and_blank_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    promo = _promo()
    audit_entry = SimpleNamespace(
        id=uuid4(),
        action="CREATE",
        details={"campaign_name": "Spring sale"},
        created_at=NOW,
    )

    async def _get_by_id(session_obj, promo_id: int):
        assert session_obj is session
        assert promo_id == promo.id
        return promo

    async def _list_for_promo(session_obj, **kwargs):
        assert session_obj is session
        assert kwargs == {"promo_code_id": promo.id, "limit": 10}
        return [(audit_entry, "admin@example.com")]

    async def _get_by_hash(session_obj, code_hash: str):
        assert session_obj is session
        assert code_hash == "hash:SPRING50"
        return promo

    monkeypatch.setattr(promo_reads, "SessionLocal", _session_local(session, session))
    monkeypatch.setattr(promo_reads.AdminRuntimePromoRepo, "get_by_id", _get_by_id)
    monkeypatch.setattr(promo_reads.PromoAuditRepo, "list_for_promo", _list_for_promo)
    monkeypatch.setattr(promo_reads.AdminRuntimePromoRepo, "get_by_hash", _get_by_hash)
    monkeypatch.setattr(promo_reads, "_code_hash", lambda raw_code: f"hash:{raw_code}")

    audit_payload = await promo_reads.list_promo_audit(promo_id=promo.id, limit=10)
    blank_code = await promo_reads.check_promo_code(code="   ")
    found_code = await promo_reads.check_promo_code(code=" spring50 ")

    assert audit_payload == {
        "items": [
            {
                "id": str(audit_entry.id),
                "action": "CREATE",
                "admin": "admin@example.com",
                "details": {"campaign_name": "Spring sale"},
                "created_at": NOW.isoformat(),
            }
        ]
    }
    assert blank_code == {"normalized_code": "", "exists": False}
    assert found_code == {"normalized_code": "SPRING50", "exists": True}


@pytest.mark.asyncio
async def test_list_promo_products_and_export_promos_cover_catalog_and_csv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    open_ended = _promo(valid_until=promo_read_catalog.OPEN_ENDED_VALID_UNTIL, campaign_name="Open")
    expiring = _promo(
        id=12,
        code_prefix="FLASH",
        campaign_name="Flash",
        valid_until=NOW + timedelta(days=5),
    )

    async def _list_codes(session_obj, **kwargs):
        assert session_obj is session
        assert kwargs["status"] is None
        assert kwargs["query"] is None
        assert kwargs["page"] == 1
        assert kwargs["limit"] == 10_000
        return [open_ended, expiring]

    monkeypatch.setattr(
        promo_read_catalog,
        "PRODUCTS",
        {
            "premium_month": object(),
            "energy_10": object(),
            "missing": object(),
            "hidden": object(),
        },
    )
    monkeypatch.setattr(
        promo_read_catalog,
        "is_product_available_for_sale",
        lambda product_code: product_code != "hidden",
    )
    monkeypatch.setattr(
        promo_read_catalog,
        "get_product",
        lambda product_code: {
            "premium_month": SimpleNamespace(
                product_code="PREMIUM_MONTH",
                title="Premium Month",
                product_type="PREMIUM",
                stars_amount=200,
            ),
            "energy_10": SimpleNamespace(
                product_code="ENERGY_10",
                title="Energy 10",
                product_type="MICRO",
                stars_amount=50,
            ),
        }.get(product_code),
    )
    monkeypatch.setattr(promo_read_catalog, "SessionLocal", _session_local(session))
    monkeypatch.setattr(promo_read_catalog.AdminRuntimePromoRepo, "list_codes", _list_codes)

    products = await promo_read_catalog.list_promo_products()
    exported = await promo_read_catalog.export_promos()
    csv_body = await _streaming_text(exported)

    assert products == {
        "items": [
            {
                "id": "ENERGY_10",
                "title": "Energy 10",
                "product_type": "MICRO",
                "stars_amount": 50,
            },
            {
                "id": "PREMIUM_MONTH",
                "title": "Premium Month",
                "product_type": "PREMIUM",
                "stars_amount": 200,
            },
        ]
    }
    assert exported.media_type == "text/csv"
    assert exported.headers["content-disposition"] == 'attachment; filename="promo_codes.csv"'
    assert "code,campaign_name,discount_type,discount_value,valid_until" in csv_body
    assert "SPRING****,Open,PERCENT,40," in csv_body
    assert f"FLASH****,Flash,PERCENT,40,{(NOW + timedelta(days=5)).isoformat()}" in csv_body
