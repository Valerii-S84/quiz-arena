from __future__ import annotations

from tests.api.admin.admin_promo_runtime_unit_support import (
    NOW,
    HTTPException,
    PromoCreateRequest,
    _admin,
    _promo,
    _session_local,
    promo_writes,
    pytest,
    timedelta,
)


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
