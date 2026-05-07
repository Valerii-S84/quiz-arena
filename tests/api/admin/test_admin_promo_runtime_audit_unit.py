from __future__ import annotations

from tests.api.admin.admin_promo_runtime_unit_support import (
    AsyncSessionStub,
    _admin,
    cast,
    promo_audit,
    pytest,
)


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
