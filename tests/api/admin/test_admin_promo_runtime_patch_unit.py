from __future__ import annotations

from tests.api.admin.admin_promo_runtime_unit_support import (
    HTTPException,
    PromoPatchRequest,
    _admin,
    _promo,
    _session_local,
    promo_writes,
    pytest,
)


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
