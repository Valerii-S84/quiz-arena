from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.economy.referrals.service import registration
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _user(user_id: int, telegram_user_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, telegram_user_id=telegram_user_id, referred_by_user_id=None)


@pytest.mark.asyncio
async def test_register_start_for_new_user_returns_none_for_blank_referral_code() -> None:
    result = await registration.register_start_for_new_user(
        AsyncSessionStub(),
        referred_user=_user(5, 50),
        referral_code="   ",
        now_utc=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
    )

    assert result is None


@pytest.mark.asyncio
async def test_register_start_for_new_user_returns_existing_status_without_creating_new_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        registration.ReferralsRepo,
        "get_by_referred_user_id",
        _async_return(SimpleNamespace(status="QUALIFIED")),
    )

    result = await registration.register_start_for_new_user(
        AsyncSessionStub(),
        referred_user=_user(5, 50),
        referral_code="ref123",
        now_utc=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
    )

    assert result == "QUALIFIED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "referrer",
    [None, _user(5, 80), _user(8, 50)],
)
async def test_register_start_for_new_user_rejects_missing_or_self_like_referrer(
    monkeypatch: pytest.MonkeyPatch,
    referrer: SimpleNamespace | None,
) -> None:
    monkeypatch.setattr(registration.ReferralsRepo, "get_by_referred_user_id", _async_return(None))
    monkeypatch.setattr(registration.UsersRepo, "get_by_referral_code", _async_return(referrer))

    result = await registration.register_start_for_new_user(
        AsyncSessionStub(),
        referred_user=_user(5, 50),
        referral_code="ref123",
        now_utc=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
    )

    assert result is None


@pytest.mark.asyncio
async def test_register_start_for_new_user_marks_reverse_pair_as_rejected_fraud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    referred_user = _user(5, 50)
    referrer = _user(8, 80)
    created: list[object] = []

    monkeypatch.setattr(registration.ReferralsRepo, "get_by_referred_user_id", _async_return(None))
    monkeypatch.setattr(registration.UsersRepo, "get_by_referral_code", _async_return(referrer))
    monkeypatch.setattr(registration.ReferralsRepo, "get_reverse_pair_since", _async_return(object()))

    async def _fake_create(_session, *, referral):
        created.append(referral)

    monkeypatch.setattr(registration.ReferralsRepo, "create", _fake_create)

    result = await registration.register_start_for_new_user(
        AsyncSessionStub(),
        referred_user=referred_user,
        referral_code=" ref123 ",
        now_utc=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
    )

    assert result == "REJECTED_FRAUD"
    assert created[0].status == "REJECTED_FRAUD"
    assert created[0].fraud_score == registration.FRAUD_SCORE_CYCLIC
    assert created[0].referral_code == "REF123"
    assert referred_user.referred_by_user_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("starts_today", "expected_status", "expected_fraud_score"),
    [
        (registration.REFERRAL_STARTS_DAILY_LIMIT - 1, "STARTED", Decimal("0")),
        (registration.REFERRAL_STARTS_DAILY_LIMIT, "REJECTED_FRAUD", registration.FRAUD_SCORE_VELOCITY),
    ],
)
async def test_register_start_for_new_user_creates_started_or_velocity_rejection(
    monkeypatch: pytest.MonkeyPatch,
    starts_today: int,
    expected_status: str,
    expected_fraud_score: Decimal,
) -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    referred_user = _user(5, 50)
    referrer = _user(8, 80)
    created: list[object] = []

    monkeypatch.setattr(registration.ReferralsRepo, "get_by_referred_user_id", _async_return(None))
    monkeypatch.setattr(registration.UsersRepo, "get_by_referral_code", _async_return(referrer))
    monkeypatch.setattr(registration.ReferralsRepo, "get_reverse_pair_since", _async_return(None))
    monkeypatch.setattr(
        registration,
        "_berlin_day_bounds_utc",
        lambda _now_utc: (_now_utc - timedelta(hours=12), _now_utc + timedelta(hours=12)),
    )
    monkeypatch.setattr(
        registration.ReferralsRepo,
        "count_referrer_starts_between",
        _async_return(starts_today),
    )

    async def _fake_create(_session, *, referral):
        created.append(referral)

    monkeypatch.setattr(registration.ReferralsRepo, "create", _fake_create)

    result = await registration.register_start_for_new_user(
        AsyncSessionStub(),
        referred_user=referred_user,
        referral_code="ref123",
        now_utc=now_utc,
    )

    assert result == expected_status
    assert created[0].status == expected_status
    assert created[0].fraud_score == expected_fraud_score
    assert referred_user.referred_by_user_id == referrer.id
