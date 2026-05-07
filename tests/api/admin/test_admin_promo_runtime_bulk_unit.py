from __future__ import annotations

from tests.api.admin.admin_promo_runtime_unit_support import (
    PromoBulkCreateRequest,
    _admin,
    _session_local,
    cast,
    promo_writes,
    pytest,
)


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
