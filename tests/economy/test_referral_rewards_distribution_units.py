from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType

import pytest

from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc


def _install_module(name: str, module: ModuleType) -> ModuleType:
    sys.modules[name] = module
    return module


def _package(name: str, path: str | None = None) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = [] if path is None else [path]
    return _install_module(name, module)


def _load_rewards_distribution_module():
    root = Path(__file__).resolve().parents[2]
    service_dir = root / "app" / "economy" / "referrals" / "service"

    _package("app", str(root / "app"))
    _package("app.db", str(root / "app" / "db"))
    _package("app.db.repo", str(root / "app" / "db" / "repo"))
    _package("app.economy", str(root / "app" / "economy"))
    _package("app.economy.referrals", str(root / "app" / "economy" / "referrals"))
    _package("app.economy.referrals.service", str(service_dir))

    referrals_repo_module = ModuleType("app.db.repo.referrals_repo")
    referrals_repo_module.ReferralsRepo = type(
        "ReferralsRepo",
        (),
        {
            "list_referrer_ids_with_reward_candidates": None,
            "list_for_referrers_for_update": None,
        },
    )
    _install_module("app.db.repo.referrals_repo", referrals_repo_module)

    constants_module = ModuleType("app.economy.referrals.constants")
    constants_module.DEFAULT_REFERRAL_REWARD_CODE = "PREMIUM_WEEK"
    constants_module.REFERRAL_REWARDS_PER_MONTH_CAP = 2
    constants_module.REWARD_DELAY = timedelta(hours=48)
    _install_module("app.economy.referrals.constants", constants_module)

    overview_module = ModuleType("app.economy.referrals.service.overview")
    overview_module._build_reward_anchors = lambda referrals: list(referrals)
    _install_module("app.economy.referrals.service.overview", overview_module)

    rewards_grant_module = ModuleType("app.economy.referrals.service.rewards_grant")

    async def _grant_reward(*_args, **_kwargs):
        return None

    rewards_grant_module._grant_reward = _grant_reward
    _install_module("app.economy.referrals.service.rewards_grant", rewards_grant_module)

    time_utils_module = ModuleType("app.economy.referrals.service.time_utils")
    time_utils_module._berlin_month_bounds_utc = lambda now_utc: (now_utc, now_utc)
    _install_module("app.economy.referrals.service.time_utils", time_utils_module)

    module_name = "app.economy.referrals.service.rewards_distribution"
    spec = importlib.util.spec_from_file_location(module_name, service_dir / "rewards_distribution.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


rewards_distribution = _load_rewards_distribution_module()


class _Session(AsyncSessionStub):
    pass


def _referral(
    referral_id: int,
    *,
    status: str = "QUALIFIED",
    qualified_at: datetime | None = None,
    rewarded_at: datetime | None = None,
    notified_at: datetime | None = None,
):
    return SimpleNamespace(
        id=referral_id,
        status=status,
        qualified_at=qualified_at,
        rewarded_at=rewarded_at,
        notified_at=notified_at,
    )


@pytest.mark.asyncio
async def test_run_reward_distribution_grants_reward_for_eligible_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    anchor = _referral(
        41,
        qualified_at=now_utc - rewards_distribution.REWARD_DELAY - timedelta(minutes=1),
    )
    granted: list[dict[str, object]] = []

    async def _fake_list_referrer_ids_with_reward_candidates(_session, **_kwargs):
        return [7]

    async def _fake_list_for_referrers_for_update(
        _session, *, referrer_user_ids: list[int]
    ):
        assert referrer_user_ids == [7]
        return {7: [anchor]}

    async def _fake_grant_reward(
        _session,
        *,
        user_id: int,
        referral_id: int,
        reward_code: str,
        now_utc: datetime,
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
        _fake_list_referrer_ids_with_reward_candidates,
    )
    monkeypatch.setattr(
        rewards_distribution.ReferralsRepo,
        "list_for_referrers_for_update",
        _fake_list_for_referrers_for_update,
    )
    monkeypatch.setattr(rewards_distribution, "_grant_reward", _fake_grant_reward)

    result = await rewards_distribution.run_reward_distribution(_Session(), now_utc=now_utc)

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
    rewarded_1 = _referral(1, status="REWARDED", rewarded_at=now_utc - timedelta(days=1))
    rewarded_2 = _referral(2, status="REWARDED", rewarded_at=now_utc - timedelta(days=2))
    fresh_anchor = _referral(
        41,
        qualified_at=now_utc - rewards_distribution.REWARD_DELAY - timedelta(minutes=1),
    )
    existing_deferred = _referral(
        42,
        status="DEFERRED_LIMIT",
        qualified_at=now_utc - rewards_distribution.REWARD_DELAY - timedelta(minutes=2),
    )
    referrals = [rewarded_1, rewarded_2, fresh_anchor, existing_deferred]

    async def _fake_list_referrer_ids_with_reward_candidates(_session, **_kwargs):
        return [7]

    async def _fake_list_for_referrers_for_update(_session, *, referrer_user_ids: list[int]):
        return {7: referrals}

    monkeypatch.setattr(
        rewards_distribution.ReferralsRepo,
        "list_referrer_ids_with_reward_candidates",
        _fake_list_referrer_ids_with_reward_candidates,
    )
    monkeypatch.setattr(
        rewards_distribution.ReferralsRepo,
        "list_for_referrers_for_update",
        _fake_list_for_referrers_for_update,
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

    result = await rewards_distribution.run_reward_distribution(_Session(), now_utc=now_utc)

    assert result["deferred_limit"] == 1
    assert fresh_anchor.status == "DEFERRED_LIMIT"
    assert existing_deferred.status == "DEFERRED_LIMIT"


@pytest.mark.asyncio
async def test_run_reward_distribution_without_reward_code_notifies_and_restores_deferred_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = datetime.now(UTC)
    anchor = _referral(
        51,
        status="DEFERRED_LIMIT",
        qualified_at=now_utc - rewards_distribution.REWARD_DELAY - timedelta(minutes=1),
    )

    async def _fake_list_referrer_ids_with_reward_candidates(_session, **_kwargs):
        return [9]

    async def _fake_list_for_referrers_for_update(_session, *, referrer_user_ids: list[int]):
        return {9: [anchor]}

    monkeypatch.setattr(
        rewards_distribution.ReferralsRepo,
        "list_referrer_ids_with_reward_candidates",
        _fake_list_referrer_ids_with_reward_candidates,
    )
    monkeypatch.setattr(
        rewards_distribution.ReferralsRepo,
        "list_for_referrers_for_update",
        _fake_list_for_referrers_for_update,
    )

    result = await rewards_distribution.run_reward_distribution(
        _Session(),
        now_utc=now_utc,
        reward_code=None,
    )

    assert result["awaiting_choice"] == 1
    assert result["newly_notified"] == 1
    assert anchor.status == "QUALIFIED"
    assert anchor.notified_at == now_utc
