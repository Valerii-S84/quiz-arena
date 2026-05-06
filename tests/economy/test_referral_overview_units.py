from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.economy.referrals.service import overview

UTC = timezone.utc


def _referral(
    referral_id: int,
    *,
    status: str,
    qualified_at: datetime | None,
    rewarded_at: datetime | None = None,
):
    return SimpleNamespace(
        id=referral_id,
        status=status,
        qualified_at=qualified_at,
        rewarded_at=rewarded_at,
    )


def test_build_reward_anchors_selects_every_third_qualified_referral() -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    referrals = [
        _referral(1, status="STARTED", qualified_at=now_utc),
        _referral(2, status="QUALIFIED", qualified_at=now_utc),
        _referral(3, status="QUALIFIED", qualified_at=now_utc),
        _referral(4, status="DEFERRED_LIMIT", qualified_at=now_utc),
        _referral(5, status="QUALIFIED", qualified_at=now_utc),
        _referral(6, status="QUALIFIED", qualified_at=now_utc),
        _referral(7, status="REWARDED", qualified_at=now_utc, rewarded_at=now_utc),
    ]

    anchors = overview._build_reward_anchors(referrals)

    assert [referral.id for referral in anchors] == [4, 7]


def test_build_overview_reports_claimable_reward_and_next_unlock_time() -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    recent_qualified_at = now_utc - timedelta(hours=1)
    old_qualified_at = now_utc - overview.REWARD_DELAY - timedelta(hours=1)
    referrals = [
        _referral(1, status="QUALIFIED", qualified_at=old_qualified_at),
        _referral(2, status="QUALIFIED", qualified_at=old_qualified_at),
        _referral(
            3, status="REWARDED", qualified_at=old_qualified_at, rewarded_at=old_qualified_at
        ),
        _referral(4, status="QUALIFIED", qualified_at=old_qualified_at),
        _referral(5, status="QUALIFIED", qualified_at=old_qualified_at),
        _referral(6, status="QUALIFIED", qualified_at=old_qualified_at),
        _referral(7, status="QUALIFIED", qualified_at=old_qualified_at),
        _referral(8, status="QUALIFIED", qualified_at=old_qualified_at),
        _referral(9, status="QUALIFIED", qualified_at=recent_qualified_at),
    ]

    result = overview._build_overview_from_referrals(
        referral_code="REF123",
        referrals=referrals,
        now_utc=now_utc,
        rewarded_this_month=1,
    )

    assert result.qualified_total == 9
    assert result.rewarded_total == 1
    assert result.pending_rewards_total == 2
    assert result.claimable_rewards == 1
    assert result.deferred_rewards == 0
    assert result.next_reward_at_utc == recent_qualified_at + overview.REWARD_DELAY


def test_build_overview_counts_deferred_rewards_when_monthly_cap_is_reached() -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    old_qualified_at = now_utc - overview.REWARD_DELAY - timedelta(hours=1)
    referrals = [
        _referral(index, status="QUALIFIED", qualified_at=old_qualified_at) for index in range(1, 7)
    ]

    result = overview._build_overview_from_referrals(
        referral_code="REF123",
        referrals=referrals,
        now_utc=now_utc,
        rewarded_this_month=overview.REFERRAL_REWARDS_PER_MONTH_CAP,
    )

    assert result.claimable_rewards == 0
    assert result.deferred_rewards == 2
    assert result.next_reward_at_utc is None


def test_build_overview_hides_claimable_rewards_while_rewards_are_locked() -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    old_qualified_at = now_utc - overview.REWARD_DELAY - timedelta(hours=1)
    referrals = [
        _referral(index, status="QUALIFIED", qualified_at=old_qualified_at) for index in range(1, 4)
    ]

    result = overview._build_overview_from_referrals(
        referral_code="REF123",
        referrals=referrals,
        now_utc=now_utc,
        rewarded_this_month=0,
        rewards_unlocked=False,
    )

    assert result.pending_rewards_total == 1
    assert result.claimable_rewards == 0
    assert result.deferred_rewards == 0
