from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.economy.referral_rewards_distribution_loader import (
    load_rewards_distribution_module,
    referral,
)
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc
rewards_distribution = load_rewards_distribution_module()


@pytest.mark.asyncio
async def test_run_reward_distribution_sets_notification_only_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    second_now_utc = first_now_utc + timedelta(hours=1)
    anchor = referral(
        51,
        qualified_at=first_now_utc - rewards_distribution.REWARD_DELAY - timedelta(minutes=1),
    )

    async def _fake_ids(_session, **_kwargs):
        return [9]

    async def _fake_referrals(_session, *, referrer_user_ids: list[int]):
        assert referrer_user_ids == [9]
        return {9: [anchor]}

    monkeypatch.setattr(
        rewards_distribution.ReferralsRepo,
        "list_referrer_ids_with_reward_candidates",
        _fake_ids,
    )
    monkeypatch.setattr(
        rewards_distribution.ReferralsRepo,
        "list_for_referrers_for_update",
        _fake_referrals,
    )

    first_result = await rewards_distribution.run_reward_distribution(
        AsyncSessionStub(),
        now_utc=first_now_utc,
        reward_code=None,
    )
    second_result = await rewards_distribution.run_reward_distribution(
        AsyncSessionStub(),
        now_utc=second_now_utc,
        reward_code=None,
    )

    assert first_result["awaiting_choice"] == 1
    assert first_result["newly_notified"] == 1
    assert second_result["awaiting_choice"] == 1
    assert second_result["newly_notified"] == 0
    assert anchor.notified_at == first_now_utc


@pytest.mark.asyncio
async def test_run_reward_distribution_grants_reward_only_once_for_same_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    second_now_utc = first_now_utc + timedelta(hours=1)
    anchor = referral(
        61,
        qualified_at=first_now_utc - rewards_distribution.REWARD_DELAY - timedelta(minutes=1),
    )
    granted: list[datetime] = []

    async def _fake_ids(_session, **_kwargs):
        return [11]

    async def _fake_referrals(_session, *, referrer_user_ids: list[int]):
        assert referrer_user_ids == [11]
        return {11: [anchor]}

    async def _fake_grant(
        _session, *, user_id: int, referral_id: int, reward_code: str, now_utc: datetime
    ) -> None:
        assert user_id == 11
        assert referral_id == 61
        assert reward_code == rewards_distribution.DEFAULT_REFERRAL_REWARD_CODE
        granted.append(now_utc)

    monkeypatch.setattr(
        rewards_distribution.ReferralsRepo,
        "list_referrer_ids_with_reward_candidates",
        _fake_ids,
    )
    monkeypatch.setattr(
        rewards_distribution.ReferralsRepo,
        "list_for_referrers_for_update",
        _fake_referrals,
    )
    monkeypatch.setattr(rewards_distribution, "_grant_reward", _fake_grant)

    first_result = await rewards_distribution.run_reward_distribution(
        AsyncSessionStub(),
        now_utc=first_now_utc,
    )
    second_result = await rewards_distribution.run_reward_distribution(
        AsyncSessionStub(),
        now_utc=second_now_utc,
    )

    assert first_result["rewards_granted"] == 1
    assert second_result["rewards_granted"] == 0
    assert granted == [first_now_utc]
    assert anchor.status == "REWARDED"
    assert anchor.rewarded_at == first_now_utc
