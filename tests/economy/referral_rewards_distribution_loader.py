from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace


def _pkg(name: str, path: str | None = None) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = [] if path is None else [path]
    return module


def load_rewards_distribution_module():
    root = Path(__file__).resolve().parents[2]
    service_dir = root / "app" / "economy" / "referrals" / "service"
    alias_pkg = "tests_referrals_service"
    alias_mod = f"{alias_pkg}.rewards_distribution"

    repo_module = ModuleType("app.db.repo.referrals_repo")
    repo_module.ReferralsRepo = type(
        "ReferralsRepo",
        (),
        {
            "list_referrer_ids_with_reward_candidates": None,
            "list_for_referrers_for_update": None,
        },
    )
    constants_module = ModuleType("app.economy.referrals.constants")
    constants_module.DEFAULT_REFERRAL_REWARD_CODE = "PREMIUM_WEEK"
    constants_module.REFERRAL_REWARDS_PER_MONTH_CAP = 2
    constants_module.REWARD_DELAY = timedelta(hours=48)

    overview_module = ModuleType(f"{alias_pkg}.overview")
    overview_module._build_reward_anchors = lambda referrals: list(referrals)

    rewards_grant_module = ModuleType(f"{alias_pkg}.rewards_grant")

    async def _grant_reward(*_args, **_kwargs):
        return None

    rewards_grant_module._grant_reward = _grant_reward

    time_utils_module = ModuleType(f"{alias_pkg}.time_utils")
    time_utils_module._berlin_month_bounds_utc = lambda now_utc: (now_utc, now_utc)

    overrides = {
        "app": _pkg("app", str(root / "app")),
        "app.db": _pkg("app.db", str(root / "app" / "db")),
        "app.db.repo": _pkg("app.db.repo", str(root / "app" / "db" / "repo")),
        "app.db.repo.referrals_repo": repo_module,
        "app.economy": _pkg("app.economy", str(root / "app" / "economy")),
        "app.economy.referrals": _pkg(
            "app.economy.referrals",
            str(root / "app" / "economy" / "referrals"),
        ),
        "app.economy.referrals.constants": constants_module,
        alias_pkg: _pkg(alias_pkg, str(service_dir)),
        f"{alias_pkg}.overview": overview_module,
        f"{alias_pkg}.rewards_grant": rewards_grant_module,
        f"{alias_pkg}.time_utils": time_utils_module,
    }
    saved = {name: sys.modules.get(name) for name in overrides}
    saved_alias = sys.modules.get(alias_mod)

    try:
        sys.modules.update(overrides)
        spec = importlib.util.spec_from_file_location(
            alias_mod, service_dir / "rewards_distribution.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[alias_mod] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        if saved_alias is None:
            sys.modules.pop(alias_mod, None)
        else:
            sys.modules[alias_mod] = saved_alias


def referral(
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
