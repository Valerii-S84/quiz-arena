from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.economy.referrals.service import queries
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


@pytest.mark.asyncio
async def test_get_referrer_overview_returns_none_for_missing_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(queries.UsersRepo, "get_by_id", _async_return(None))

    result = await queries.get_referrer_overview(
        AsyncSessionStub(),
        user_id=7,
        now_utc=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
    )

    assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(("paid_count", "rewards_unlocked"), [(0, False), (2, True)])
async def test_get_referrer_overview_builds_view_model_with_purchase_lock_state(
    monkeypatch: pytest.MonkeyPatch,
    paid_count: int,
    rewards_unlocked: bool,
) -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    calls: list[dict[str, object]] = []
    user = SimpleNamespace(referral_code="REF123")
    referrals = [SimpleNamespace(id=1)]
    sentinel = object()

    monkeypatch.setattr(queries.UsersRepo, "get_by_id", _async_return(user))
    monkeypatch.setattr(queries.ReferralsRepo, "list_for_referrer", _async_return(referrals))
    monkeypatch.setattr(
        queries,
        "_berlin_month_bounds_utc",
        lambda _now_utc: (_now_utc, _now_utc),
    )
    monkeypatch.setattr(
        queries.ReferralsRepo,
        "count_rewards_for_referrer_between",
        _async_return(3),
    )
    monkeypatch.setattr(
        queries.PurchasesRepo,
        "count_paid_purchases_for_user",
        _async_return(paid_count),
    )

    def _fake_build(**kwargs):
        calls.append(kwargs)
        return sentinel

    monkeypatch.setattr(queries, "_build_overview_from_referrals", _fake_build)

    result = await queries.get_referrer_overview(AsyncSessionStub(), user_id=7, now_utc=now_utc)

    assert result is sentinel
    assert calls == [
        {
            "referral_code": "REF123",
            "referrals": referrals,
            "now_utc": now_utc,
            "rewarded_this_month": 3,
            "rewards_unlocked": rewards_unlocked,
        }
    ]
