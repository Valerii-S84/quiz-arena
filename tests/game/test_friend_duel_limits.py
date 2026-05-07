from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.game.duels import limits as duel_limits
from app.game.duels.limits import DUEL_ACCESS_FREE
from tests.type_helpers import AsyncSessionStub

MAY_BERLIN_DAY_START_UTC = datetime(2026, 4, 30, 22, 0, tzinfo=UTC)
JAN_BERLIN_DAY_START_UTC = datetime(2026, 1, 15, 23, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_friend_create_free_quota_uses_berlin_day_start_in_repo_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    _patch_friend_limit_dependencies(monkeypatch, free_used_today=0, captured=captured)

    access_type = await duel_limits.DuelLimitService.resolve_friend_create_access_type(
        AsyncSessionStub(),
        creator_user_id=11,
        now_utc=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
    )

    assert access_type == DUEL_ACCESS_FREE
    assert captured["friend_since"] == MAY_BERLIN_DAY_START_UTC
    assert captured["friend_access_type"] == DUEL_ACCESS_FREE
    assert captured["friend_creator_user_id"] == 11


@pytest.mark.asyncio
async def test_friend_create_after_berlin_midnight_does_not_count_previous_day_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    _patch_friend_limit_dependencies(monkeypatch, free_used_today=0, captured=captured)

    access_type = await duel_limits.DuelLimitService.resolve_friend_create_access_type(
        AsyncSessionStub(),
        creator_user_id=11,
        now_utc=datetime(2026, 4, 30, 22, 30, tzinfo=UTC),
    )

    assert access_type == DUEL_ACCESS_FREE
    assert captured["friend_since"] == MAY_BERLIN_DAY_START_UTC


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "now_utc",
    [
        datetime(2026, 1, 15, 23, 30, tzinfo=UTC),
        datetime(2026, 1, 16, 0, 59, tzinfo=UTC),
    ],
)
async def test_friend_create_uses_same_berlin_day_start_during_early_local_hours(
    monkeypatch: pytest.MonkeyPatch,
    now_utc: datetime,
) -> None:
    captured: dict[str, object] = {}
    _patch_friend_limit_dependencies(monkeypatch, free_used_today=0, captured=captured)

    access_type = await duel_limits.DuelLimitService.resolve_friend_create_access_type(
        AsyncSessionStub(),
        creator_user_id=11,
        now_utc=now_utc,
    )

    assert access_type == DUEL_ACCESS_FREE
    assert captured["friend_since"] == JAN_BERLIN_DAY_START_UTC


def _patch_friend_limit_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    free_used_today: int,
    captured: dict[str, object] | None = None,
) -> None:
    capture = captured if captured is not None else {}

    async def _get_user(*_args, **_kwargs):
        return SimpleNamespace(id=11)

    async def _has_premium(*_args, **_kwargs):
        return False

    async def _count_friend_duels(*_args, **kwargs):
        capture["friend_creator_user_id"] = kwargs["creator_user_id"]
        capture["friend_access_type"] = kwargs["access_type"]
        capture["friend_since"] = kwargs["since"]
        return free_used_today

    monkeypatch.setattr(duel_limits.UsersRepo, "get_by_id_for_update", _get_user)
    monkeypatch.setattr(duel_limits.EntitlementsRepo, "has_active_premium", _has_premium)
    monkeypatch.setattr(
        duel_limits.FriendChallengesRepo,
        "count_by_creator_access_type_excluding_arena_revanche",
        _count_friend_duels,
    )
