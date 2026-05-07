from __future__ import annotations

from tests.economy.referral_rewards_claim_units_support import (
    UTC,
    SimpleNamespace,
    _anchor,
    _overview,
    _Session,
    datetime,
    pytest,
    rewards_claim,
    timedelta,
)


@pytest.mark.asyncio
async def test_claim_next_reward_choice_claims_reward_and_updates_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    user = SimpleNamespace(referral_code="REF-CLAIM")
    referrals = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    anchor = _anchor(
        referral_id=43, qualified_at=now_utc - rewards_claim.REWARD_DELAY - timedelta(minutes=1)
    )
    granted: list[dict[str, object]] = []

    async def _fake_get_by_id(_session, _user_id):
        return user

    async def _fake_list_for_referrer_for_update(_session, *, referrer_user_id: int):
        return referrals

    async def _fake_count_rewards_for_referrer_between(_session, **_kwargs):
        return 0

    async def _fake_count_paid_purchases_for_user(_session, *, user_id: int):
        assert user_id == 7
        return 1

    async def _fake_grant_reward(
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

    def _fake_build_reward_anchors(_referrals):
        return [anchor]

    def _fake_build_overview_from_referrals(
        *,
        referral_code: str,
        referrals,
        now_utc: datetime,
        rewarded_this_month: int,
        rewards_unlocked: bool,
    ):
        assert rewarded_this_month == 1
        assert rewards_unlocked is True
        return _overview("claimed")

    monkeypatch.setattr(rewards_claim.UsersRepo, "get_by_id", _fake_get_by_id)
    monkeypatch.setattr(
        rewards_claim.ReferralsRepo,
        "list_for_referrer_for_update",
        _fake_list_for_referrer_for_update,
    )
    monkeypatch.setattr(
        rewards_claim.ReferralsRepo,
        "count_rewards_for_referrer_between",
        _fake_count_rewards_for_referrer_between,
    )
    monkeypatch.setattr(
        rewards_claim.PurchasesRepo,
        "count_paid_purchases_for_user",
        _fake_count_paid_purchases_for_user,
    )
    monkeypatch.setattr(rewards_claim, "_grant_reward", _fake_grant_reward)
    monkeypatch.setattr(rewards_claim, "_build_reward_anchors", _fake_build_reward_anchors)
    monkeypatch.setattr(
        rewards_claim, "_build_overview_from_referrals", _fake_build_overview_from_referrals
    )

    result = await rewards_claim.claim_next_reward_choice(
        _Session(),
        user_id=7,
        reward_code=rewards_claim.REWARD_CODE_PREMIUM_WEEK,
        now_utc=now_utc,
    )

    assert result is not None
    assert result.status == "CLAIMED"
    assert result.reward_code == rewards_claim.REWARD_CODE_PREMIUM_WEEK
    assert granted == [
        {
            "user_id": 7,
            "referral_id": 43,
            "reward_code": rewards_claim.REWARD_CODE_PREMIUM_WEEK,
            "now_utc": now_utc,
        }
    ]
    assert anchor.status == "REWARDED"
    assert anchor.rewarded_at == now_utc
