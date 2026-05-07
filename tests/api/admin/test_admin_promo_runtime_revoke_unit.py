from __future__ import annotations

from tests.api.admin.admin_promo_runtime_unit_support import (
    UTC,
    HTTPException,
    _admin,
    _promo,
    _session_local,
    cast,
    datetime,
    promo_writes_status,
    pytest,
)


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
