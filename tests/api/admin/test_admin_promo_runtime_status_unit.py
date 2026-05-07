from __future__ import annotations

from tests.api.admin.admin_promo_runtime_unit_support import (
    HTTPException,
    _admin,
    _promo,
    _session_local,
    promo_writes_status,
    pytest,
)


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
