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
async def test_run_reward_distribution_grants_reward_for_eligible_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    anchor = referral(
        41,
        qualified_at=now_utc - rewards_distribution.REWARD_DELAY - timedelta(minutes=1),
    )
    granted: list[dict[str, object]] = []

    async def _fake_ids(_session, **_kwargs):
        return [7]

    async def _fake_referrals(_session, *, referrer_user_ids: list[int]):
        assert referrer_user_ids == [7]
        return {7: [anchor]}

    async def _fake_grant(
        _session, *, user_id: int, referral_id: int, reward_code: str, now_utc: datetime
    ):
        granted.append(
            {
                "user_id": user_id,
                "referral_id": referral_id,
                "reward_code": reward_code,
                "now_utc": now_utc,
            }
        )

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

    result = await rewards_distribution.run_reward_distribution(AsyncSessionStub(), now_utc=now_utc)

    assert result == {
        "referrers_examined": 1,
        "rewards_granted": 1,
        "deferred_limit": 0,
        "awaiting_choice": 0,
        "newly_notified": 0,
    }
    assert anchor.status == "REWARDED"
    assert anchor.rewarded_at == now_utc
    assert granted[0]["reward_code"] == rewards_distribution.DEFAULT_REFERRAL_REWARD_CODE


@pytest.mark.asyncio
async def test_run_reward_distribution_marks_only_newly_deferred_rewards_at_monthly_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    referrals = [
        referral(1, status="REWARDED", rewarded_at=now_utc - timedelta(days=1)),
        referral(2, status="REWARDED", rewarded_at=now_utc - timedelta(days=2)),
    ]
    fresh_anchor = referral(
        41,
        qualified_at=now_utc - rewards_distribution.REWARD_DELAY - timedelta(minutes=1),
    )
    existing_deferred = referral(
        42,
        status="DEFERRED_LIMIT",
        qualified_at=now_utc - rewards_distribution.REWARD_DELAY - timedelta(minutes=2),
    )
    referrals.extend([fresh_anchor, existing_deferred])

    async def _fake_ids(_session, **_kwargs):
        return [7]

    async def _fake_referrals(_session, *, referrer_user_ids: list[int]):
        assert referrer_user_ids == [7]
        return {7: referrals}

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
    monkeypatch.setattr(
        rewards_distribution,
        "_build_reward_anchors",
        lambda _referrals: [fresh_anchor, existing_deferred],
    )
    monkeypatch.setattr(
        rewards_distribution,
        "_berlin_month_bounds_utc",
        lambda _now_utc: (now_utc - timedelta(days=3), now_utc + timedelta(days=1)),
    )

    result = await rewards_distribution.run_reward_distribution(AsyncSessionStub(), now_utc=now_utc)

    assert result["deferred_limit"] == 1
    assert fresh_anchor.status == "DEFERRED_LIMIT"
    assert existing_deferred.status == "DEFERRED_LIMIT"
