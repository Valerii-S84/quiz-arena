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


def _referral(referral_id: int, *, created_at: datetime):
    return SimpleNamespace(
        id=referral_id,
        status="STARTED",
        referrer_user_id=7,
        referred_user_id=8,
        created_at=created_at,
        fraud_score=0,
        qualified_at=None,
    )


def _user(user_id: int):
    return SimpleNamespace(id=user_id, status="ACTIVE")


@pytest.mark.asyncio
async def test_run_qualification_checks_marks_referral_as_qualified_when_thresholds_met(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    started = _referral(4, created_at=now_utc - timedelta(days=3))

    monkeypatch.setattr(qualification.ReferralsRepo, "list_started_ids", _async_return([4]))
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
    monkeypatch.setattr(qualification.UsersRepo, "get_by_id", _async_return(_user(1)))
    monkeypatch.setattr(
        qualification.QuizAttemptsRepo,
        "count_user_attempts_between",
        _async_return(qualification.QUALIFICATION_MIN_ATTEMPTS),
    )
    monkeypatch.setattr(
        qualification.QuizAttemptsRepo,
        "count_user_active_local_days_between",
        _async_return(qualification.QUALIFICATION_MIN_LOCAL_DAYS),
    )

    result = await qualification.run_qualification_checks(AsyncSessionStub(), now_utc=now_utc)

    assert result["qualified"] == 1
    assert started.status == "QUALIFIED"
    assert started.qualified_at == now_utc


@pytest.mark.asyncio
async def test_run_qualification_checks_cancels_after_window_when_thresholds_not_met(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_at = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)
    now_utc = created_at + qualification.QUALIFICATION_WINDOW + timedelta(minutes=1)
    started = _referral(5, created_at=created_at)

    monkeypatch.setattr(qualification.ReferralsRepo, "list_started_ids", _async_return([5]))
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
    monkeypatch.setattr(qualification.UsersRepo, "get_by_id", _async_return(_user(1)))
    monkeypatch.setattr(
        qualification.QuizAttemptsRepo,
        "count_user_attempts_between",
        _async_return(qualification.QUALIFICATION_MIN_ATTEMPTS - 1),
    )
    monkeypatch.setattr(
        qualification.QuizAttemptsRepo,
        "count_user_active_local_days_between",
        _async_return(qualification.QUALIFICATION_MIN_LOCAL_DAYS - 1),
    )

    result = await qualification.run_qualification_checks(AsyncSessionStub(), now_utc=now_utc)

    assert result["canceled"] == 1
    assert started.status == "CANCELED"
    assert started.qualified_at is None
