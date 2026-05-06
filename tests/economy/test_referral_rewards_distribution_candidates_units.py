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
async def test_run_reward_distribution_without_candidates_returns_zero_counters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_ids(_session, **_kwargs):
        return []

    async def _fake_referrals(_session, *, referrer_user_ids: list[int]):
        assert referrer_user_ids == []
        return {}

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

    result = await rewards_distribution.run_reward_distribution(
        AsyncSessionStub(),
        now_utc=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
    )

    assert result == {
        "referrers_examined": 0,
        "rewards_granted": 0,
        "deferred_limit": 0,
        "awaiting_choice": 0,
        "newly_notified": 0,
    }


@pytest.mark.asyncio
async def test_run_reward_distribution_skips_referrer_without_reward_anchors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eligible = referral(31, qualified_at=datetime(2026, 2, 18, 9, 0, tzinfo=UTC))

    async def _fake_ids(_session, **_kwargs):
        return [5]

    async def _fake_referrals(_session, *, referrer_user_ids: list[int]):
        assert referrer_user_ids == [5]
        return {5: [eligible]}

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
    monkeypatch.setattr(rewards_distribution, "_build_reward_anchors", lambda _referrals: [])

    result = await rewards_distribution.run_reward_distribution(
        AsyncSessionStub(),
        now_utc=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
    )

    assert result["referrers_examined"] == 1
    assert result["rewards_granted"] == 0
    assert result["deferred_limit"] == 0
    assert result["awaiting_choice"] == 0
    assert result["newly_notified"] == 0
    assert eligible.status == "QUALIFIED"


@pytest.mark.asyncio
async def test_run_reward_distribution_skips_reward_when_delay_has_not_elapsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    anchor = referral(
        41,
        qualified_at=now_utc - rewards_distribution.REWARD_DELAY + timedelta(minutes=1),
    )

    async def _fake_ids(_session, **_kwargs):
        return [7]

    async def _fake_referrals(_session, *, referrer_user_ids: list[int]):
        assert referrer_user_ids == [7]
        return {7: [anchor]}

    async def _unexpected_grant(*_args, **_kwargs):
        raise AssertionError("reward grant must not be called before delay elapses")

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
    monkeypatch.setattr(rewards_distribution, "_grant_reward", _unexpected_grant)

    result = await rewards_distribution.run_reward_distribution(
        AsyncSessionStub(),
        now_utc=now_utc,
    )

    assert result["rewards_granted"] == 0
    assert anchor.status == "QUALIFIED"
    assert anchor.rewarded_at is None
