from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import user_onboarding


@pytest.mark.asyncio
async def test_get_by_id_delegates_to_users_repo(monkeypatch) -> None:
    expected_user = SimpleNamespace(id=17)
    captured: dict[str, object] = {}

    async def _fake_get_by_id(session, user_id: int):
        captured["session"] = session
        captured["user_id"] = user_id
        return expected_user

    monkeypatch.setattr(user_onboarding.UsersRepo, "get_by_id", _fake_get_by_id)
    session = object()

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
    session = object()

    result = await user_onboarding.UserOnboardingService.get_by_telegram_user_id(
        session,
        700_001,
    )

    assert result is expected_user
    assert captured == {"session": session, "telegram_user_id": 700_001}
