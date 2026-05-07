from __future__ import annotations

from tests.api.admin.admin_promo_runtime_unit_support import (
    _admin,
    _promo,
    _session_local,
    promo_reads,
    pytest,
)


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
