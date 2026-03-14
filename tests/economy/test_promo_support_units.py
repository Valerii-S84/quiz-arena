from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.economy.promo.idempotency as promo_idempotency
import app.economy.promo.redeem_validation as promo_validation
from app.economy.promo.errors import PromoExpiredError, PromoInvalidError, PromoNotApplicableError

UTC = timezone.utc


def _promo_code(**overrides: object) -> SimpleNamespace:
    now_utc = datetime.now(UTC)
    payload: dict[str, object] = {
        "id": 21,
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
        "grant_premium_days": None,
        "new_users_only": False,
        "first_purchase_only": False,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class _Session:
    def __init__(self, entitlement: object | None = None) -> None:
        self._entitlement = entitlement

    async def get(self, _model, _pk):
        return self._entitlement


@pytest.mark.asyncio
async def test_build_idempotent_result_rejects_missing_promo_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_code_by_id(_session, _promo_code_id):
        return None

    monkeypatch.setattr(promo_idempotency.PromoRepo, "get_code_by_id", _fake_get_code_by_id)

    with pytest.raises(PromoInvalidError):
        await promo_idempotency.build_idempotent_result(
            _Session(),
            redemption=SimpleNamespace(
                id=uuid4(),
                promo_code_id=21,
                grant_entitlement_id=None,
                reserved_until=None,
            ),
        )


@pytest.mark.asyncio
async def test_build_idempotent_result_returns_premium_grant_without_entitlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_code_by_id(_session, _promo_code_id):
        return _promo_code(promo_type="PREMIUM_GRANT", grant_premium_days=7, discount_percent=None)

    monkeypatch.setattr(promo_idempotency.PromoRepo, "get_code_by_id", _fake_get_code_by_id)

    result = await promo_idempotency.build_idempotent_result(
        _Session(),
        redemption=SimpleNamespace(
            id=uuid4(),
            promo_code_id=21,
            grant_entitlement_id=None,
            reserved_until=None,
        ),
    )

    assert result.result_type == "PREMIUM_GRANT"
    assert result.idempotent_replay is True
    assert result.premium_days == 7
    assert result.premium_ends_at is None


@pytest.mark.asyncio
async def test_build_idempotent_result_returns_percent_discount_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    promo_code = _promo_code(applicable_products=["ENERGY_10", "PREMIUM_STARTER"])

    async def _fake_get_code_by_id(_session, _promo_code_id):
        return promo_code

    monkeypatch.setattr(promo_idempotency.PromoRepo, "get_code_by_id", _fake_get_code_by_id)
    reserved_until = datetime.now(UTC) + timedelta(minutes=15)
    result = await promo_idempotency.build_idempotent_result(
        _Session(),
        redemption=SimpleNamespace(
            id=uuid4(),
            promo_code_id=21,
            grant_entitlement_id=None,
            reserved_until=reserved_until,
        ),
    )

    assert result.result_type == "PERCENT_DISCOUNT"
    assert result.discount_type == "PERCENT"
    assert result.discount_value == 40
    assert result.reserved_until == reserved_until
    assert result.applicable_products == ["ENERGY_10", "PREMIUM_STARTER"]


@pytest.mark.asyncio
async def test_ensure_code_is_current_rejects_expired_code_and_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_attempts: list[dict[str, object]] = []

    async def _fake_record_failed_attempt(**payload):
        failed_attempts.append(payload)

    with pytest.raises(PromoExpiredError):
        await promo_validation.ensure_code_is_current(
            promo_code=_promo_code(
                status="INACTIVE",
                valid_until=datetime.now(UTC) - timedelta(minutes=1),
            ),
            user_id=7,
            code_hash="hash:expired",
            now_utc=datetime.now(UTC),
            record_failed_attempt=_fake_record_failed_attempt,
        )

    assert failed_attempts[0]["result"] == "EXPIRED"
    assert failed_attempts[0]["normalized_code_hash"] == "hash:expired"


@pytest.mark.asyncio
async def test_ensure_code_is_current_rejects_depleted_code_and_records_reason() -> None:
    failed_attempts: list[dict[str, object]] = []

    async def _fake_record_failed_attempt(**payload):
        failed_attempts.append(payload)

    with pytest.raises(PromoExpiredError):
        await promo_validation.ensure_code_is_current(
            promo_code=_promo_code(max_total_uses=1, used_total=1),
            user_id=7,
            code_hash="hash:depleted",
            now_utc=datetime.now(UTC),
            record_failed_attempt=_fake_record_failed_attempt,
        )

    assert failed_attempts[0]["metadata"] == {"reason": "DEPLETED"}


@pytest.mark.asyncio
async def test_ensure_purchase_eligibility_rejects_new_users_only_after_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_attempts: list[dict[str, object]] = []

    async def _fake_count_by_user(_session, *, user_id: int) -> int:
        assert user_id == 7
        return 1

    async def _fake_record_failed_attempt(**payload):
        failed_attempts.append(payload)

    monkeypatch.setattr(promo_validation.PurchasesRepo, "count_by_user", _fake_count_by_user)

    with pytest.raises(PromoNotApplicableError):
        await promo_validation.ensure_purchase_eligibility(
            object(),
            promo_code=_promo_code(new_users_only=True),
            user_id=7,
            code_hash="hash:new-user-only",
            now_utc=datetime.now(UTC),
            record_failed_attempt=_fake_record_failed_attempt,
        )

    assert failed_attempts[0]["metadata"] == {"reason": "NEW_USERS_ONLY"}


@pytest.mark.asyncio
async def test_ensure_purchase_eligibility_rejects_first_purchase_only_after_purchase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_attempts: list[dict[str, object]] = []

    async def _fake_count_by_user(_session, *, user_id: int) -> int:
        assert user_id == 7
        return 2

    async def _fake_record_failed_attempt(**payload):
        failed_attempts.append(payload)

    monkeypatch.setattr(promo_validation.PurchasesRepo, "count_by_user", _fake_count_by_user)

    with pytest.raises(PromoNotApplicableError):
        await promo_validation.ensure_purchase_eligibility(
            object(),
            promo_code=_promo_code(first_purchase_only=True),
            user_id=7,
            code_hash="hash:first-purchase-only",
            now_utc=datetime.now(UTC),
            record_failed_attempt=_fake_record_failed_attempt,
        )

    assert failed_attempts[0]["metadata"] == {"reason": "FIRST_PURCHASE_ONLY"}
