from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.economy.promo.service as promo_service
from app.economy.promo.errors import PromoNotApplicableError
from app.economy.promo.types import PromoRedeemResult

UTC = timezone.utc


def _promo_code(**overrides: object) -> SimpleNamespace:
    now_utc = datetime.now(UTC)
    payload: dict[str, object] = {
        "id": 11,
        "promo_type": "PERCENT_DISCOUNT",
        "discount_type": "PERCENT",
        "discount_value": None,
        "discount_percent": 40,
        "target_scope": "ENERGY_10",
        "applicable_products": None,
        "status": "ACTIVE",
        "valid_from": now_utc - timedelta(days=1),
        "valid_until": now_utc + timedelta(days=1),
        "max_total_uses": 10,
        "used_total": 0,
        "max_uses_per_user": 1,
        "grant_premium_days": None,
        "updated_at": now_utc,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


@pytest.mark.asyncio
async def test_redeem_applies_premium_grant_and_records_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    recorded_attempts: list[dict[str, object]] = []
    promo_code = _promo_code(
        id=12,
        promo_type="PREMIUM_GRANT",
        discount_type=None,
        discount_percent=None,
        grant_premium_days=7,
        target_scope="PREMIUM_STARTER",
    )

    async def _fake_get_redemption_by_idempotency_key_for_update(_session, _idempotency_key):
        return None

    async def _fake_get_by_id(_session, _user_id):
        return SimpleNamespace(id=7)

    async def _fake_enforce_rate_limit(_session, *, user_id: int, now_utc: datetime) -> None:
        return None

    async def _fake_get_code_by_hash_for_update(_session, _code_hash):
        return promo_code

    async def _fake_list_redemptions_by_code_and_user_for_update(
        _session, *, promo_code_id: int, user_id: int
    ):
        assert promo_code_id == 12
        assert user_id == 7
        return []

    async def _fake_noop(*_args, **_kwargs):
        return None

    async def _fake_create_redemption(_session, *, redemption):
        return redemption

    async def _fake_apply_premium_grant_redemption(
        _session,
        *,
        user_id: int,
        redemption,
        now_utc: datetime,
        promo_code: SimpleNamespace,
        apply_premium_grant,
    ):
        assert user_id == 7
        assert promo_code.id == 12
        assert callable(apply_premium_grant)
        return PromoRedeemResult(
            redemption_id=redemption.id,
            result_type="PREMIUM_GRANT",
            idempotent_replay=False,
            premium_days=7,
        )

    async def _fake_record_attempt(_session, **payload):
        recorded_attempts.append(payload)

    monkeypatch.setattr(
        promo_service.PromoRepo,
        "get_redemption_by_idempotency_key_for_update",
        _fake_get_redemption_by_idempotency_key_for_update,
    )
    monkeypatch.setattr(promo_service.UsersRepo, "get_by_id", _fake_get_by_id)
    monkeypatch.setattr(promo_service.PromoService, "_enforce_rate_limit", _fake_enforce_rate_limit)
    monkeypatch.setattr(
        promo_service.PromoRepo,
        "get_code_by_hash_for_update",
        _fake_get_code_by_hash_for_update,
    )
    monkeypatch.setattr(
        promo_service.PromoRepo,
        "list_redemptions_by_code_and_user_for_update",
        _fake_list_redemptions_by_code_and_user_for_update,
    )
    monkeypatch.setattr(promo_service, "ensure_retry_allowed", _fake_noop)
    monkeypatch.setattr(promo_service, "ensure_code_is_current", _fake_noop)
    monkeypatch.setattr(promo_service, "ensure_purchase_eligibility", _fake_noop)
    monkeypatch.setattr(promo_service.PromoRepo, "create_redemption", _fake_create_redemption)
    monkeypatch.setattr(
        promo_service,
        "apply_premium_grant_redemption",
        _fake_apply_premium_grant_redemption,
    )
    monkeypatch.setattr(promo_service.PromoService, "_record_attempt", _fake_record_attempt)
    monkeypatch.setattr(promo_service, "normalize_promo_code", lambda code: code.strip().upper())
    monkeypatch.setattr(
        promo_service,
        "hash_promo_code",
        lambda *, normalized_code, pepper: f"{pepper}:{normalized_code}",
    )
    monkeypatch.setattr(
        promo_service,
        "get_settings",
        lambda: SimpleNamespace(promo_secret_pepper="pepper"),
    )

    result = await promo_service.PromoService.redeem(
        object(),
        user_id=7,
        promo_code="grant7",
        idempotency_key="idem-5",
        now_utc=now_utc,
    )

    assert result.result_type == "PREMIUM_GRANT"
    assert result.idempotent_replay is False
    assert result.premium_days == 7
    assert recorded_attempts[0]["result"] == "ACCEPTED"
    assert recorded_attempts[0]["source"] == "API"


@pytest.mark.asyncio
async def test_redeem_rejects_misconfigured_percent_discount_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    promo_code = _promo_code(discount_type=None, discount_percent=None)

    async def _fake_get_redemption_by_idempotency_key_for_update(_session, _idempotency_key):
        return None

    async def _fake_get_by_id(_session, _user_id):
        return SimpleNamespace(id=7)

    async def _fake_enforce_rate_limit(_session, *, user_id: int, now_utc: datetime) -> None:
        return None

    async def _fake_get_code_by_hash_for_update(_session, _code_hash):
        return promo_code

    async def _fake_list_redemptions_by_code_and_user_for_update(
        _session, *, promo_code_id: int, user_id: int
    ):
        return []

    async def _fake_noop(*_args, **_kwargs):
        return None

    async def _fake_create_redemption(_session, *, redemption):
        return redemption

    monkeypatch.setattr(
        promo_service.PromoRepo,
        "get_redemption_by_idempotency_key_for_update",
        _fake_get_redemption_by_idempotency_key_for_update,
    )
    monkeypatch.setattr(promo_service.UsersRepo, "get_by_id", _fake_get_by_id)
    monkeypatch.setattr(promo_service.PromoService, "_enforce_rate_limit", _fake_enforce_rate_limit)
    monkeypatch.setattr(
        promo_service.PromoRepo,
        "get_code_by_hash_for_update",
        _fake_get_code_by_hash_for_update,
    )
    monkeypatch.setattr(
        promo_service.PromoRepo,
        "list_redemptions_by_code_and_user_for_update",
        _fake_list_redemptions_by_code_and_user_for_update,
    )
    monkeypatch.setattr(promo_service, "ensure_retry_allowed", _fake_noop)
    monkeypatch.setattr(promo_service, "ensure_code_is_current", _fake_noop)
    monkeypatch.setattr(promo_service, "ensure_purchase_eligibility", _fake_noop)
    monkeypatch.setattr(promo_service.PromoRepo, "create_redemption", _fake_create_redemption)
    monkeypatch.setattr(promo_service, "normalize_promo_code", lambda code: code.strip().upper())
    monkeypatch.setattr(
        promo_service,
        "hash_promo_code",
        lambda *, normalized_code, pepper: f"{pepper}:{normalized_code}",
    )
    monkeypatch.setattr(
        promo_service,
        "get_settings",
        lambda: SimpleNamespace(promo_secret_pepper="pepper"),
    )

    with pytest.raises(PromoNotApplicableError):
        await promo_service.PromoService.redeem(
            object(),
            user_id=7,
            promo_code="save40",
            idempotency_key="idem-6",
            now_utc=datetime.now(UTC),
        )
