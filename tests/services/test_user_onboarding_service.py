from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.services import user_onboarding
from tests.type_helpers import AsyncSessionStub


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_get_by_id_delegates_to_users_repo(monkeypatch) -> None:
    expected_user = SimpleNamespace(id=17)
    captured: dict[str, object] = {}

    async def _fake_get_by_id(session, user_id: int):
        captured["session"] = session
        captured["user_id"] = user_id
        return expected_user

    monkeypatch.setattr(user_onboarding.UsersRepo, "get_by_id", _fake_get_by_id)
    session = _Session()

    result = await user_onboarding.UserOnboardingService.get_by_id(session, 17)

    assert result is expected_user
    assert captured == {"session": session, "user_id": 17}


@pytest.mark.asyncio
async def test_get_by_telegram_user_id_delegates_to_users_repo(monkeypatch) -> None:
    expected_user = SimpleNamespace(id=23)
    captured: dict[str, object] = {}

    async def _fake_get_by_telegram_user_id(session, telegram_user_id: int):
        captured["session"] = session
        captured["telegram_user_id"] = telegram_user_id
        return expected_user

    monkeypatch.setattr(
        user_onboarding.UsersRepo,
        "get_by_telegram_user_id",
        _fake_get_by_telegram_user_id,
    )
    session = _Session()

    result = await user_onboarding.UserOnboardingService.get_by_telegram_user_id(
        session,
        700_001,
    )

    assert result is expected_user
    assert captured == {"session": session, "telegram_user_id": 700_001}


@pytest.mark.asyncio
async def test_touch_existing_user_updates_last_seen_without_home_snapshot(monkeypatch) -> None:
    expected_user = SimpleNamespace(id=23)
    now_utc = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)
    captured: dict[str, object] = {}

    async def _fake_get_by_telegram_user_id(session, telegram_user_id: int):
        captured["lookup"] = (session, telegram_user_id)
        return expected_user

    async def _fake_touch_last_seen(session, user_id: int, seen_at):
        captured["touch"] = (session, user_id, seen_at)
        return 1

    monkeypatch.setattr(
        user_onboarding.UsersRepo,
        "get_by_telegram_user_id",
        _fake_get_by_telegram_user_id,
    )
    monkeypatch.setattr(user_onboarding.UsersRepo, "touch_last_seen", _fake_touch_last_seen)
    session = _Session()

    result = await user_onboarding.UserOnboardingService.touch_existing_user(
        session,
        telegram_user=SimpleNamespace(id=700_001),
        now_utc=now_utc,
    )

    assert result is expected_user
    assert captured == {
        "lookup": (session, 700_001),
        "touch": (session, 23, now_utc),
    }
