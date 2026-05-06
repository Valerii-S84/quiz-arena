from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.economy.referrals.service import qualification
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _referral(referral_id: int, *, created_at: datetime, referrer_user_id: int = 7, referred_user_id: int = 8):
    return SimpleNamespace(
        id=referral_id,
        status="STARTED",
        referrer_user_id=referrer_user_id,
        referred_user_id=referred_user_id,
        created_at=created_at,
        fraud_score=0,
        qualified_at=None,
    )


def _user(user_id: int, *, status: str = "ACTIVE"):
    return SimpleNamespace(id=user_id, status=status)


@pytest.mark.asyncio
async def test_run_qualification_checks_rejects_reverse_pair_as_fraud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    started = _referral(1, created_at=now_utc - timedelta(days=1), referrer_user_id=42, referred_user_id=91)
    rejected: list[tuple[int, int]] = []

    monkeypatch.setattr(qualification.ReferralsRepo, "list_started_ids", _async_return([1]))

    async def _fake_get_by_id(_session, *, referral_id: int):
        assert referral_id == 1
        return started

    async def _fake_rejected(referral_id: int, referrer_user_id: int) -> None:
        rejected.append((referral_id, referrer_user_id))

    monkeypatch.setattr(qualification.ReferralsRepo, "get_by_id_for_update", _fake_get_by_id)
    monkeypatch.setattr(
        qualification.ReferralsRepo,
        "get_reverse_pair_since",
        _async_return(object()),
    )

    result = await qualification.run_qualification_checks(
        AsyncSessionStub(),
        now_utc=now_utc,
        on_rejected_fraud=_fake_rejected,
    )

    assert result == {"examined": 1, "qualified": 0, "canceled": 0, "rejected_fraud": 1}
    assert started.status == "REJECTED_FRAUD"
    assert started.fraud_score == qualification.FRAUD_SCORE_CYCLIC
    assert rejected == [(1, 42)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("deleted_referrer", "deleted_referred"),
    [(True, False), (False, True)],
)
async def test_run_qualification_checks_cancels_when_participant_is_deleted(
    monkeypatch: pytest.MonkeyPatch,
    deleted_referrer: bool,
    deleted_referred: bool,
) -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    started = _referral(2, created_at=now_utc - timedelta(days=1))

    monkeypatch.setattr(qualification.ReferralsRepo, "list_started_ids", _async_return([2]))
    monkeypatch.setattr(
        qualification.ReferralsRepo,
        "get_by_id_for_update",
        _async_return(started),
    )
    monkeypatch.setattr(
        qualification.ReferralsRepo,
        "get_reverse_pair_since",
        _async_return(None),
    )

    async def _fake_user(_session, user_id: int):
        if user_id == started.referrer_user_id and deleted_referrer:
            return _user(user_id, status="DELETED")
        if user_id == started.referred_user_id and deleted_referred:
            return _user(user_id, status="DELETED")
        return _user(user_id)

    monkeypatch.setattr(qualification.UsersRepo, "get_by_id", _fake_user)

    result = await qualification.run_qualification_checks(AsyncSessionStub(), now_utc=now_utc)

    assert result["canceled"] == 1
    assert started.status == "CANCELED"
