from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.economy.referrals.service.rewards_claim as rewards_claim

UTC = timezone.utc


def _overview(status: str) -> SimpleNamespace:
    return SimpleNamespace(status=status)


def _anchor(
    *,
    referral_id: int,
    status: str = "QUALIFIED",
    qualified_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=referral_id,
        status=status,
        qualified_at=qualified_at,
        rewarded_at=None,
    )


@pytest.mark.asyncio
async def test_claim_next_reward_choice_rejects_unsupported_reward_code() -> None:
    with pytest.raises(ValueError):
        await rewards_claim.claim_next_reward_choice(
            object(),
            user_id=7,
            reward_code="bad-code",
            now_utc=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_claim_next_reward_choice_returns_none_for_missing_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_by_id(_session, _user_id):
        return None

    monkeypatch.setattr(rewards_claim.UsersRepo, "get_by_id", _fake_get_by_id)

    result = await rewards_claim.claim_next_reward_choice(
        object(),
        user_id=7,
        reward_code=rewards_claim.REWARD_CODE_PREMIUM_STARTER,
        now_utc=datetime.now(UTC),
    )

    assert result is None


@pytest.mark.asyncio
async def test_claim_next_reward_choice_returns_monthly_cap_and_marks_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    user = SimpleNamespace(referral_code="REF-CAP")
    referrals = [SimpleNamespace(id=1)]
    anchor = _anchor(
        referral_id=41, qualified_at=now_utc - rewards_claim.REWARD_DELAY - timedelta(minutes=1)
    )

    async def _fake_get_by_id(_session, _user_id):
        return user

    async def _fake_list_for_referrer_for_update(_session, *, referrer_user_id: int):
        return referrals

    async def _fake_count_rewards_for_referrer_between(_session, **_kwargs):
        return rewards_claim.REFERRAL_REWARDS_PER_MONTH_CAP

    def _fake_build_reward_anchors(_referrals):
        return [anchor]

    def _fake_build_overview_from_referrals(
        *, referral_code: str, referrals, now_utc: datetime, rewarded_this_month: int
    ):
        assert referral_code == "REF-CAP"
        assert referrals is referrals
        assert rewarded_this_month == rewards_claim.REFERRAL_REWARDS_PER_MONTH_CAP
        return _overview("cap")

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
    monkeypatch.setattr(rewards_claim, "_build_reward_anchors", _fake_build_reward_anchors)
    monkeypatch.setattr(
        rewards_claim, "_build_overview_from_referrals", _fake_build_overview_from_referrals
    )

    result = await rewards_claim.claim_next_reward_choice(
        object(),
        user_id=7,
        reward_code=rewards_claim.REWARD_CODE_PREMIUM_STARTER,
        now_utc=now_utc,
    )

    assert result is not None
    assert result.status == "MONTHLY_CAP"
    assert result.reward_code is None
    assert anchor.status == "DEFERRED_LIMIT"


@pytest.mark.asyncio
async def test_claim_next_reward_choice_returns_too_early_for_delayed_reward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    user = SimpleNamespace(referral_code="REF-EARLY")
    anchor = _anchor(referral_id=42, qualified_at=now_utc - timedelta(hours=1))
    captured: list[dict[str, object]] = []

    async def _fake_get_by_id(_session, _user_id):
        return user

    async def _fake_list_for_referrer_for_update(_session, *, referrer_user_id: int):
        return [anchor]

    async def _fake_count_rewards_for_referrer_between(_session, **_kwargs):
        return 0

    def _fake_build_reward_anchors(_referrals):
        return [anchor]

    def _fake_build_overview_from_referrals(
        *, referral_code: str, referrals, now_utc: datetime, rewarded_this_month: int
    ):
        captured.append(
            {
                "referral_code": referral_code,
                "rewarded_this_month": rewarded_this_month,
            }
        )
        return _overview("early")

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
    monkeypatch.setattr(rewards_claim, "_build_reward_anchors", _fake_build_reward_anchors)
    monkeypatch.setattr(
        rewards_claim, "_build_overview_from_referrals", _fake_build_overview_from_referrals
    )

    result = await rewards_claim.claim_next_reward_choice(
        object(),
        user_id=7,
        reward_code=rewards_claim.REWARD_CODE_PREMIUM_STARTER,
        now_utc=now_utc,
    )

    assert result is not None
    assert result.status == "TOO_EARLY"
    assert result.reward_code is None
    assert captured[0]["referral_code"] == "REF-EARLY"


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
        *, referral_code: str, referrals, now_utc: datetime, rewarded_this_month: int
    ):
        assert rewarded_this_month == 1
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
    monkeypatch.setattr(rewards_claim, "_grant_reward", _fake_grant_reward)
    monkeypatch.setattr(rewards_claim, "_build_reward_anchors", _fake_build_reward_anchors)
    monkeypatch.setattr(
        rewards_claim, "_build_overview_from_referrals", _fake_build_overview_from_referrals
    )

    result = await rewards_claim.claim_next_reward_choice(
        object(),
        user_id=7,
        reward_code=rewards_claim.REWARD_CODE_PREMIUM_STARTER,
        now_utc=now_utc,
    )

    assert result is not None
    assert result.status == "CLAIMED"
    assert result.reward_code == rewards_claim.REWARD_CODE_PREMIUM_STARTER
    assert granted == [
        {
            "user_id": 7,
            "referral_id": 43,
            "reward_code": rewards_claim.REWARD_CODE_PREMIUM_STARTER,
            "now_utc": now_utc,
        }
    ]
    assert anchor.status == "REWARDED"
    assert anchor.rewarded_at == now_utc
