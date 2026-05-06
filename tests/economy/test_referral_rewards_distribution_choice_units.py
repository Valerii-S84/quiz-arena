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
async def test_run_reward_distribution_without_reward_code_notifies_and_restores_deferred_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    anchor = referral(
        51,
        status="DEFERRED_LIMIT",
        qualified_at=now_utc - rewards_distribution.REWARD_DELAY - timedelta(minutes=1),
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

    result = await rewards_distribution.run_reward_distribution(
        AsyncSessionStub(),
        now_utc=now_utc,
        reward_code=None,
    )

    assert result["awaiting_choice"] == 1
    assert result["newly_notified"] == 1
    assert anchor.status == "QUALIFIED"
    assert anchor.notified_at == now_utc
