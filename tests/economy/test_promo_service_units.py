from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.economy.promo.service as promo_service
from app.economy.promo.errors import (
    PromoIdempotencyConflictError,
    PromoInvalidError,
    PromoRateLimitedError,
    PromoUserNotFoundError,
)
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
async def test_redeem_returns_idempotent_result_for_same_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = SimpleNamespace(id=uuid4(), user_id=7)
    expected = PromoRedeemResult(
        redemption_id=existing.id,
        result_type="PERCENT_DISCOUNT",
        idempotent_replay=True,
    )

    async def _fake_get_redemption_by_idempotency_key_for_update(_session, _idempotency_key):
        return existing

    async def _fake_build_idempotent_result(_session, *, redemption):
        assert redemption is existing
        return expected

    monkeypatch.setattr(
        promo_service.PromoRepo,
        "get_redemption_by_idempotency_key_for_update",
        _fake_get_redemption_by_idempotency_key_for_update,
    )
    monkeypatch.setattr(
        promo_service.PromoService, "_build_idempotent_result", _fake_build_idempotent_result
    )

    result = await promo_service.PromoService.redeem(
        object(),
        user_id=7,
        promo_code="SAVE40",
        idempotency_key="idem-1",
        now_utc=datetime.now(UTC),
    )

    assert result is expected


@pytest.mark.asyncio
async def test_redeem_rejects_idempotency_conflict_for_other_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_redemption_by_idempotency_key_for_update(_session, _idempotency_key):
        return SimpleNamespace(id=uuid4(), user_id=8)

    monkeypatch.setattr(
        promo_service.PromoRepo,
        "get_redemption_by_idempotency_key_for_update",
        _fake_get_redemption_by_idempotency_key_for_update,
    )

    with pytest.raises(PromoIdempotencyConflictError):
        await promo_service.PromoService.redeem(
            object(),
            user_id=7,
            promo_code="SAVE40",
            idempotency_key="idem-1",
            now_utc=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_redeem_rejects_missing_user(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_get_redemption_by_idempotency_key_for_update(_session, _idempotency_key):
        return None

    async def _fake_get_by_id(_session, _user_id):
        return None

    monkeypatch.setattr(
        promo_service.PromoRepo,
        "get_redemption_by_idempotency_key_for_update",
        _fake_get_redemption_by_idempotency_key_for_update,
    )
    monkeypatch.setattr(promo_service.UsersRepo, "get_by_id", _fake_get_by_id)

    with pytest.raises(PromoUserNotFoundError):
        await promo_service.PromoService.redeem(
            object(),
            user_id=7,
            promo_code="SAVE40",
            idempotency_key="idem-1",
            now_utc=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_redeem_records_rate_limit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    failed_attempts: list[dict[str, object]] = []

    async def _fake_get_redemption_by_idempotency_key_for_update(_session, _idempotency_key):
        return None

    async def _fake_get_by_id(_session, _user_id):
        return SimpleNamespace(id=7)

    async def _fake_enforce_rate_limit(_session, *, user_id: int, now_utc: datetime) -> None:
        assert user_id == 7
        assert now_utc.tzinfo is UTC
        raise PromoRateLimitedError

    async def _fake_record_failed_attempt(**payload):
        failed_attempts.append(payload)

    monkeypatch.setattr(
        promo_service.PromoRepo,
        "get_redemption_by_idempotency_key_for_update",
        _fake_get_redemption_by_idempotency_key_for_update,
    )
    monkeypatch.setattr(promo_service.UsersRepo, "get_by_id", _fake_get_by_id)
    monkeypatch.setattr(promo_service.PromoService, "_enforce_rate_limit", _fake_enforce_rate_limit)
    monkeypatch.setattr(
        promo_service.PromoService,
        "_record_failed_attempt",
        _fake_record_failed_attempt,
    )
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

    with pytest.raises(PromoRateLimitedError):
        await promo_service.PromoService.redeem(
            object(),
            user_id=7,
            promo_code=" save40 ",
            idempotency_key="idem-2",
            now_utc=datetime.now(UTC),
        )

    assert failed_attempts == [
        {
            "user_id": 7,
            "normalized_code_hash": "pepper:SAVE40",
            "result": "RATE_LIMITED",
            "now_utc": failed_attempts[0]["now_utc"],
            "metadata": {"idempotency_key": "idem-2"},
            "source": "API",
        }
    ]


@pytest.mark.asyncio
async def test_redeem_rejects_empty_code_and_records_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_attempts: list[dict[str, object]] = []

    async def _fake_get_redemption_by_idempotency_key_for_update(_session, _idempotency_key):
        return None

    async def _fake_get_by_id(_session, _user_id):
        return SimpleNamespace(id=7)

    async def _fake_enforce_rate_limit(_session, *, user_id: int, now_utc: datetime) -> None:
        return None

    async def _fake_record_failed_attempt(**payload):
        failed_attempts.append(payload)

    monkeypatch.setattr(
        promo_service.PromoRepo,
        "get_redemption_by_idempotency_key_for_update",
        _fake_get_redemption_by_idempotency_key_for_update,
    )
    monkeypatch.setattr(promo_service.UsersRepo, "get_by_id", _fake_get_by_id)
    monkeypatch.setattr(promo_service.PromoService, "_enforce_rate_limit", _fake_enforce_rate_limit)
    monkeypatch.setattr(
        promo_service.PromoService,
        "_record_failed_attempt",
        _fake_record_failed_attempt,
    )
    monkeypatch.setattr(promo_service, "normalize_promo_code", lambda _code: "")
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

    with pytest.raises(PromoInvalidError):
        await promo_service.PromoService.redeem(
            object(),
            user_id=7,
            promo_code="   ",
            idempotency_key="idem-3",
            now_utc=datetime.now(UTC),
        )

    assert failed_attempts[0]["result"] == "INVALID"
    assert failed_attempts[0]["metadata"] == {"reason": "EMPTY"}
    assert failed_attempts[0]["source"] == "API"


@pytest.mark.asyncio
async def test_redeem_rejects_unknown_code_and_records_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_attempts: list[dict[str, object]] = []

    async def _fake_get_redemption_by_idempotency_key_for_update(_session, _idempotency_key):
        return None

    async def _fake_get_by_id(_session, _user_id):
        return SimpleNamespace(id=7)

    async def _fake_enforce_rate_limit(_session, *, user_id: int, now_utc: datetime) -> None:
        return None

    async def _fake_record_failed_attempt(**payload):
        failed_attempts.append(payload)

    async def _fake_get_code_by_hash_for_update(_session, _code_hash):
        return None

    monkeypatch.setattr(
        promo_service.PromoRepo,
        "get_redemption_by_idempotency_key_for_update",
        _fake_get_redemption_by_idempotency_key_for_update,
    )
    monkeypatch.setattr(promo_service.UsersRepo, "get_by_id", _fake_get_by_id)
    monkeypatch.setattr(promo_service.PromoService, "_enforce_rate_limit", _fake_enforce_rate_limit)
    monkeypatch.setattr(
        promo_service.PromoService,
        "_record_failed_attempt",
        _fake_record_failed_attempt,
    )
    monkeypatch.setattr(
        promo_service.PromoRepo,
        "get_code_by_hash_for_update",
        _fake_get_code_by_hash_for_update,
    )
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

    with pytest.raises(PromoInvalidError):
        await promo_service.PromoService.redeem(
            object(),
            user_id=7,
            promo_code="save40",
            idempotency_key="idem-4",
            now_utc=datetime.now(UTC),
        )

    assert failed_attempts[0]["normalized_code_hash"] == "pepper:SAVE40"
    assert failed_attempts[0]["result"] == "INVALID"
    assert failed_attempts[0]["source"] == "API"
