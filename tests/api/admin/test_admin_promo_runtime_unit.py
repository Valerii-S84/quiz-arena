from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.admin import deps as admin_deps
from app.api.routes.admin import promo_audit, promo_reads, promo_writes, promo_writes_status
from app.api.routes.admin.promo_models import (
    PromoBulkCreateRequest,
    PromoCreateRequest,
    PromoPatchRequest,
)
from tests.type_helpers import AsyncBeginContext, AsyncSessionStub, build_promo_code

NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def _session_local(*sessions: object) -> SimpleNamespace:
    remaining = list(sessions)
    return SimpleNamespace(begin=lambda: AsyncBeginContext(remaining.pop(0)))


def _admin(*, role: str = "admin") -> admin_deps.AdminPrincipal:
    return admin_deps.AdminPrincipal(
        id=uuid4(),
        email="admin@example.com",
        role=role,
        two_factor_verified=True,
        client_ip="127.0.0.1",
    )


def _promo(**overrides: object):
    payload = {
        "id": 77,
        "code_prefix": "SPRING",
        "campaign_name": "Spring sale",
        "valid_from": NOW - timedelta(days=1),
        "valid_until": NOW + timedelta(days=365),
        "created_at": NOW - timedelta(days=2),
        "updated_at": NOW - timedelta(hours=1),
    }
    payload.update(overrides)
    return build_promo_code(**payload)


@pytest.mark.asyncio
async def test_create_promo_valid_returns_serialized_payload_and_writes_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    admin = _admin()
    audit_calls: list[dict[str, object]] = []

    async def _get_by_hash(session_obj, code_hash: str):
        assert session_obj is session
        assert code_hash == "hash:SPRING50"
        return None

    async def _create(session_obj, promo):
        assert session_obj is session
        assert promo.id == 5001
        assert promo.code_prefix == "SPRING50"
        assert promo.discount_type == "PERCENT"
        assert promo.discount_percent == 50
        assert promo.max_total_uses is None
        assert promo.max_uses_per_user == 1
        return promo

    async def _audit(session_obj, **kwargs):
        assert session_obj is session
        audit_calls.append(kwargs)

    monkeypatch.setattr(promo_writes, "SessionLocal", _session_local(session))
    monkeypatch.setattr(promo_writes, "build_promo_id", lambda: 5001)
    monkeypatch.setattr(promo_writes, "code_hash_from_raw", lambda raw_code: f"hash:{raw_code}")
    monkeypatch.setattr(
        promo_writes, "encrypt_promo_code", lambda raw_code: raw_code.encode("ascii")
    )
    monkeypatch.setattr(promo_writes.AdminRuntimePromoRepo, "get_by_hash", _get_by_hash)
    monkeypatch.setattr(promo_writes.AdminRuntimePromoRepo, "create", _create)
    monkeypatch.setattr(promo_writes, "write_promo_audit", _audit)

    payload = PromoCreateRequest(
        code=" spring50 ",
        campaign_name="Fruehling",
        discount_type="PERCENT",
        discount_value=50,
        applicable_products=["premium_month"],
        max_total_uses=0,
        max_per_user=1,
        valid_from=NOW,
        valid_until=NOW + timedelta(days=10),
    )

    response = await promo_writes.create_promo(payload=payload, admin=admin)

    assert response["raw_code"] == "SPRING50"
    assert response["can_reveal_code"] is False
    assert response["discount_type"] == "PERCENT"
    assert response["discount_value"] == 50
    assert response["max_total_uses"] == 0
    assert response["applicable_products"] == ["PREMIUM_MONTH"]
    assert len(audit_calls) == 1
    assert audit_calls[0]["action"] == "CREATE"
    assert audit_calls[0]["promo_code_id"] == 5001
    assert audit_calls[0]["admin_id"] == admin.id
    assert audit_calls[0]["details"] == {
        "campaign_name": "Fruehling",
        "discount_type": "PERCENT",
        "discount_value": 50,
        "applicable_products": ["PREMIUM_MONTH"],
        "valid_from": NOW.isoformat(),
        "valid_until": (NOW + timedelta(days=10)).isoformat(),
        "max_total_uses": 0,
        "max_per_user": 1,
    }


@pytest.mark.asyncio
async def test_create_promo_rejects_duplicate_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    admin = _admin()

    async def _get_by_hash(session_obj, code_hash: str):
        assert session_obj is session
        assert code_hash == "hash:SPRING50"
        return _promo()

    monkeypatch.setattr(promo_writes, "SessionLocal", _session_local(session))
    monkeypatch.setattr(promo_writes, "code_hash_from_raw", lambda raw_code: f"hash:{raw_code}")
    monkeypatch.setattr(
        promo_writes, "encrypt_promo_code", lambda raw_code: raw_code.encode("ascii")
    )
    monkeypatch.setattr(promo_writes.AdminRuntimePromoRepo, "get_by_hash", _get_by_hash)

    payload = PromoCreateRequest(code="spring50", discount_type="PERCENT", discount_value=50)

    with pytest.raises(HTTPException) as exc_info:
        await promo_writes.create_promo(payload=payload, admin=admin)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {"code": "E_PROMO_CODE_EXISTS"}


@pytest.mark.asyncio
async def test_create_promo_returns_500_when_encryption_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin = _admin()

    monkeypatch.setattr(
        promo_writes,
        "encrypt_promo_code",
        lambda raw_code: (_ for _ in ()).throw(ValueError("boom")),
    )

    payload = PromoCreateRequest(code="spring50", discount_type="PERCENT", discount_value=50)

    with pytest.raises(HTTPException) as exc_info:
        await promo_writes.create_promo(payload=payload, admin=admin)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == {"code": "E_PROMO_ENCRYPTION_UNAVAILABLE"}


@pytest.mark.asyncio
async def test_create_bulk_promos_returns_generated_codes_and_bulk_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    admin = _admin(role="super_admin")
    audit_calls: list[dict[str, object]] = []

    async def _list_existing_hashes(session_obj, code_hashes: list[str]):
        assert session_obj is session
        assert code_hashes == ["hash:MASSAAAA", "hash:MASSBBBB"]
        return set()

    async def _bulk_create(session_obj, promos):
        assert session_obj is session
        assert [promo.code_prefix for promo in promos] == ["MASSAAAA", "MASSBBBB"]
        assert all(promo.discount_type == "FREE" for promo in promos)
        return promos

    async def _audit(session_obj, **kwargs):
        assert session_obj is session
        audit_calls.append(kwargs)

    monkeypatch.setattr(promo_writes, "SessionLocal", _session_local(session))
    ids = iter([7001, 7002])

    monkeypatch.setattr(
        promo_writes,
        "build_generated_codes",
        lambda prefix, count: ["MASSAAAA", "MASSBBBB"],
    )
    monkeypatch.setattr(promo_writes, "build_promo_id", lambda: next(ids))
    monkeypatch.setattr(promo_writes, "code_hash_from_raw", lambda raw_code: f"hash:{raw_code}")
    monkeypatch.setattr(
        promo_writes, "encrypt_promo_code", lambda raw_code: raw_code.encode("ascii")
    )
    monkeypatch.setattr(
        promo_writes.AdminRuntimePromoRepo, "list_existing_hashes", _list_existing_hashes
    )
    monkeypatch.setattr(promo_writes.AdminRuntimePromoRepo, "bulk_create", _bulk_create)
    monkeypatch.setattr(promo_writes, "write_promo_audit", _audit)

    payload = PromoBulkCreateRequest(
        count=2,
        prefix="mass",
        campaign_name="Massenversand",
        discount_type="FREE",
        max_total_uses=1,
        max_per_user=1,
    )

    response = await promo_writes.create_bulk_promos(payload=payload, admin=admin)
    items = cast(list[dict[str, object]], response["items"])

    assert response["generated"] == 2
    assert response["count"] == 2
    assert response["codes"] == ["MASSAAAA", "MASSBBBB"]
    assert [item["raw_code"] for item in items] == ["MASSAAAA", "MASSBBBB"]
    assert all(item["can_reveal_code"] is True for item in items)
    assert len(audit_calls) == 1
    assert audit_calls[0]["admin_id"] == admin.id
    assert audit_calls[0]["action"] == "BULK_GENERATE"
    assert audit_calls[0]["promo_code_id"] is None
    assert audit_calls[0]["details"] == {"count": 2}


@pytest.mark.asyncio
async def test_patch_promo_supports_legacy_percent_mapping_and_max_uses_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    admin = _admin()
    promo = _promo(max_total_uses=10, max_uses_per_user=1, target_scope="ANY")
    audit_calls: list[dict[str, object]] = []

    async def _get_by_id_for_update(session_obj, promo_id: int):
        assert session_obj is session
        assert promo_id == promo.id
        return promo

    async def _audit(session_obj, **kwargs):
        assert session_obj is session
        audit_calls.append(kwargs)

    monkeypatch.setattr(promo_writes, "SessionLocal", _session_local(session))
    monkeypatch.setattr(
        promo_writes.AdminRuntimePromoRepo, "get_by_id_for_update", _get_by_id_for_update
    )
    monkeypatch.setattr(promo_writes, "write_promo_audit", _audit)

    payload = PromoPatchRequest(
        type="discount_percent",
        value=25,
        product_id="energy_10",
        max_uses=0,
        max_per_user=3,
    )

    response = await promo_writes.patch_promo(promo_id=promo.id, payload=payload, admin=admin)

    assert response["discount_type"] == "PERCENT"
    assert response["discount_value"] == 25
    assert response["applicable_products"] == ["ENERGY_10"]
    assert response["max_total_uses"] == 0
    assert response["max_per_user"] == 3
    assert promo.discount_type == "PERCENT"
    assert promo.discount_percent == 25
    assert promo.target_scope == "ENERGY_10"
    assert promo.max_total_uses is None
    assert promo.max_uses_per_user == 3
    assert len(audit_calls) == 1
    assert audit_calls[0]["action"] == "UPDATE"


@pytest.mark.asyncio
async def test_patch_promo_returns_not_found_for_missing_promo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    admin = _admin()

    async def _get_by_id_for_update(session_obj, promo_id: int):
        assert session_obj is session
        assert promo_id == 404
        return None

    monkeypatch.setattr(promo_writes, "SessionLocal", _session_local(session))
    monkeypatch.setattr(
        promo_writes.AdminRuntimePromoRepo,
        "get_by_id_for_update",
        _get_by_id_for_update,
    )

    with pytest.raises(HTTPException) as exc_info:
        await promo_writes.patch_promo(
            promo_id=404,
            payload=PromoPatchRequest(campaign_name="Missing"),
            admin=admin,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {"code": "E_PROMO_NOT_FOUND"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initial_status", "expected_status", "expected_action"),
    [
        ("ACTIVE", "PAUSED", "DEACTIVATE"),
        ("PAUSED", "ACTIVE", "ACTIVATE"),
    ],
)
async def test_toggle_promo_switches_status_and_logs_action(
    monkeypatch: pytest.MonkeyPatch,
    initial_status: str,
    expected_status: str,
    expected_action: str,
) -> None:
    session = object()
    admin = _admin()
    promo = _promo(status=initial_status)
    audit_calls: list[dict[str, object]] = []

    async def _get_by_id_for_update(session_obj, promo_id: int):
        assert session_obj is session
        assert promo_id == promo.id
        return promo

    async def _audit(session_obj, **kwargs):
        assert session_obj is session
        audit_calls.append(kwargs)

    monkeypatch.setattr(promo_writes_status, "SessionLocal", _session_local(session))
    monkeypatch.setattr(
        promo_writes_status.AdminRuntimePromoRepo,
        "get_by_id_for_update",
        _get_by_id_for_update,
    )
    monkeypatch.setattr(promo_writes_status, "write_promo_audit", _audit)

    response = await promo_writes_status.toggle_promo(promo_id=promo.id, admin=admin)

    assert response["status"] == ("inactive" if expected_status == "PAUSED" else "active")
    assert promo.status == expected_status
    assert len(audit_calls) == 1
    assert audit_calls[0]["admin_id"] == admin.id
    assert audit_calls[0]["action"] == expected_action
    assert audit_calls[0]["promo_code_id"] == promo.id
    assert audit_calls[0]["details"] == {"status": expected_status}


@pytest.mark.asyncio
async def test_toggle_promo_rejects_missing_and_conflicting_statuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_missing = object()
    session_conflict = object()
    admin = _admin()
    paused_forever = _promo(status="EXPIRED")

    async def _missing(session_obj, promo_id: int):
        assert session_obj is session_missing
        assert promo_id == 404
        return None

    async def _conflict(session_obj, promo_id: int):
        assert session_obj is session_conflict
        assert promo_id == paused_forever.id
        return paused_forever

    monkeypatch.setattr(
        promo_writes_status,
        "SessionLocal",
        _session_local(session_missing, session_conflict),
    )
    monkeypatch.setattr(
        promo_writes_status.AdminRuntimePromoRepo,
        "get_by_id_for_update",
        _missing,
    )

    with pytest.raises(HTTPException) as missing_exc:
        await promo_writes_status.toggle_promo(promo_id=404, admin=admin)

    assert missing_exc.value.status_code == 404
    assert missing_exc.value.detail == {"code": "E_PROMO_NOT_FOUND"}

    monkeypatch.setattr(
        promo_writes_status.AdminRuntimePromoRepo,
        "get_by_id_for_update",
        _conflict,
    )

    with pytest.raises(HTTPException) as conflict_exc:
        await promo_writes_status.toggle_promo(promo_id=paused_forever.id, admin=admin)

    assert conflict_exc.value.status_code == 409
    assert conflict_exc.value.detail == {"code": "E_PROMO_STATUS_CONFLICT"}


@pytest.mark.asyncio
async def test_revoke_promo_returns_count_and_trimmed_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    admin = _admin()
    promo = _promo()
    audit_calls: list[dict[str, object]] = []
    revoked_rows = [object(), object()]

    async def _get_by_id_for_update(session_obj, promo_id: int):
        assert session_obj is session
        assert promo_id == promo.id
        return promo

    async def _revoke_reserved(session_obj, promo_id: int, now_utc: datetime):
        assert session_obj is session
        assert promo_id == promo.id
        assert now_utc.tzinfo == UTC
        return revoked_rows

    async def _audit(session_obj, **kwargs):
        assert session_obj is session
        audit_calls.append(kwargs)

    monkeypatch.setattr(promo_writes_status, "SessionLocal", _session_local(session))
    monkeypatch.setattr(
        promo_writes_status.AdminRuntimePromoRepo,
        "get_by_id_for_update",
        _get_by_id_for_update,
    )
    monkeypatch.setattr(
        promo_writes_status.AdminRuntimePromoRepo,
        "revoke_active_reserved_redemptions",
        _revoke_reserved,
    )
    monkeypatch.setattr(promo_writes_status, "write_promo_audit", _audit)

    response = await promo_writes_status.revoke_promo(
        promo_id=promo.id,
        payload=promo_writes_status.PromoRevokeRequest(reason="  misuse  "),
        admin=admin,
    )
    promo_payload = cast(dict[str, object], response["promo"])

    assert response["revoked_count"] == 2
    assert response["reason"] == "misuse"
    assert promo_payload["code"] == "SPRING****"
    assert len(audit_calls) == 1
    assert audit_calls[0]["admin_id"] == admin.id
    assert audit_calls[0]["action"] == "REVOKE"
    assert audit_calls[0]["promo_code_id"] == promo.id
    assert audit_calls[0]["details"] == {"revoked_count": 2, "reason": "misuse"}


@pytest.mark.asyncio
async def test_revoke_promo_supports_none_reason_and_missing_promo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_ok = object()
    session_missing = object()
    admin = _admin()
    promo = _promo()
    audit_calls: list[dict[str, object]] = []

    async def _ok(session_obj, promo_id: int):
        assert session_obj is session_ok
        assert promo_id == promo.id
        return promo

    async def _missing(session_obj, promo_id: int):
        assert session_obj is session_missing
        assert promo_id == 404
        return None

    async def _revoke_reserved(session_obj, promo_id: int, now_utc: datetime):
        assert session_obj is session_ok
        assert promo_id == promo.id
        assert now_utc.tzinfo == UTC
        return []

    async def _audit(session_obj, **kwargs):
        assert session_obj is session_ok
        audit_calls.append(kwargs)

    monkeypatch.setattr(
        promo_writes_status,
        "SessionLocal",
        _session_local(session_ok, session_missing),
    )
    monkeypatch.setattr(
        promo_writes_status.AdminRuntimePromoRepo,
        "revoke_active_reserved_redemptions",
        _revoke_reserved,
    )
    monkeypatch.setattr(promo_writes_status, "write_promo_audit", _audit)
    monkeypatch.setattr(
        promo_writes_status.AdminRuntimePromoRepo,
        "get_by_id_for_update",
        _ok,
    )

    response = await promo_writes_status.revoke_promo(
        promo_id=promo.id,
        payload=None,
        admin=admin,
    )

    assert response["revoked_count"] == 0
    assert response["reason"] is None
    assert audit_calls[0]["details"] == {"revoked_count": 0, "reason": None}

    monkeypatch.setattr(
        promo_writes_status.AdminRuntimePromoRepo,
        "get_by_id_for_update",
        _missing,
    )

    with pytest.raises(HTTPException) as exc_info:
        await promo_writes_status.revoke_promo(
            promo_id=404,
            payload=None,
            admin=admin,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == {"code": "E_PROMO_NOT_FOUND"}


@pytest.mark.asyncio
async def test_get_promo_for_non_super_admin_keeps_raw_code_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    promo = _promo(code_encrypted=b"ciphertext")

    async def _get_by_id(session_obj, promo_id: int):
        assert session_obj is session
        assert promo_id == promo.id
        return promo

    async def _unexpected(*args, **kwargs):
        raise AssertionError("reveal and audit should not run for non-super-admin")

    monkeypatch.setattr(promo_reads, "SessionLocal", _session_local(session))
    monkeypatch.setattr(promo_reads.AdminRuntimePromoRepo, "get_by_id", _get_by_id)
    monkeypatch.setattr(promo_reads, "decrypt_promo_code", _unexpected)
    monkeypatch.setattr(promo_reads, "write_admin_audit", _unexpected)
    monkeypatch.setattr(promo_reads, "write_promo_audit", _unexpected)

    response = await promo_reads.get_promo(promo_id=promo.id, admin=_admin(), reveal=True)

    assert response["code"] == "SPRING****"
    assert response["raw_code"] is None
    assert response["can_reveal_code"] is False


@pytest.mark.asyncio
async def test_get_promo_for_super_admin_reveals_raw_code_and_writes_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = object()
    admin = _admin(role="super_admin")
    promo = _promo(code_encrypted=b"ciphertext")
    admin_audits: list[dict[str, object]] = []
    promo_audits: list[dict[str, object]] = []

    async def _get_by_id(session_obj, promo_id: int):
        assert session_obj is session
        assert promo_id == promo.id
        return promo

    async def _write_admin_audit(session_obj, **kwargs):
        assert session_obj is session
        admin_audits.append(kwargs)

    async def _write_promo_audit(session_obj, **kwargs):
        assert session_obj is session
        promo_audits.append(kwargs)

    monkeypatch.setattr(promo_reads, "SessionLocal", _session_local(session))
    monkeypatch.setattr(promo_reads.AdminRuntimePromoRepo, "get_by_id", _get_by_id)
    monkeypatch.setattr(promo_reads, "decrypt_promo_code", lambda ciphertext: "SECRET30")
    monkeypatch.setattr(promo_reads, "write_admin_audit", _write_admin_audit)
    monkeypatch.setattr(promo_reads, "write_promo_audit", _write_promo_audit)

    response = await promo_reads.get_promo(
        promo_id=promo.id,
        admin=admin,
        reveal=True,
    )

    assert response["raw_code"] == "SECRET30"
    assert response["can_reveal_code"] is True
    assert admin_audits == [
        {
            "admin_email": "admin@example.com",
            "action": "promo_reveal_code",
            "target_type": "promo_code",
            "target_id": str(promo.id),
            "payload": {"code_prefix": "SPRING"},
            "ip": "127.0.0.1",
        }
    ]
    assert len(promo_audits) == 1
    assert promo_audits[0]["admin_id"] == admin.id
    assert promo_audits[0]["action"] == "REVEAL_CODE"
    assert promo_audits[0]["promo_code_id"] == promo.id
    assert promo_audits[0]["details"] == {"code_prefix": "SPRING"}


@pytest.mark.asyncio
async def test_write_promo_audit_delegates_to_repo_log(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = cast(AsyncSessionStub, object())
    admin = _admin()
    calls: list[dict[str, object]] = []

    async def _log(session_obj, **kwargs):
        assert session_obj is session
        calls.append(kwargs)

    monkeypatch.setattr(promo_audit.PromoAuditRepo, "log", _log)

    await promo_audit.write_promo_audit(
        session,
        admin_id=admin.id,
        action="CREATE",
        promo_code_id=77,
        details={"campaign_name": "Spring sale"},
    )

    assert calls == [
        {
            "admin_id": admin.id,
            "action": "CREATE",
            "promo_code_id": 77,
            "details": {"campaign_name": "Spring sale"},
        }
    ]
