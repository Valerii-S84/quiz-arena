from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.economy.referrals.service import prompt
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


@pytest.mark.asyncio
async def test_reserve_post_game_prompt_returns_false_for_missing_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompt.UsersRepo, "get_by_id_for_update", _async_return(None))

    result = await prompt.reserve_post_game_prompt(
        AsyncSessionStub(),
        user_id=7,
        now_utc=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
    )

    assert result is False


@pytest.mark.asyncio
async def test_reserve_post_game_prompt_returns_false_when_prompt_already_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(referral_prompt_shown_at=datetime(2026, 2, 19, 12, 0, tzinfo=UTC))
    monkeypatch.setattr(prompt.UsersRepo, "get_by_id_for_update", _async_return(user))

    result = await prompt.reserve_post_game_prompt(
        AsyncSessionStub(),
        user_id=7,
        now_utc=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
    )

    assert result is False


@pytest.mark.asyncio
@pytest.mark.parametrize("completed_sessions", [0, 3])
async def test_reserve_post_game_prompt_requires_first_or_second_completed_session(
    monkeypatch: pytest.MonkeyPatch,
    completed_sessions: int,
) -> None:
    user = SimpleNamespace(referral_prompt_shown_at=None)
    monkeypatch.setattr(prompt.UsersRepo, "get_by_id_for_update", _async_return(user))
    monkeypatch.setattr(
        prompt.QuizSessionsRepo,
        "count_completed_for_user",
        _async_return(completed_sessions),
    )

    result = await prompt.reserve_post_game_prompt(
        AsyncSessionStub(),
        user_id=7,
        now_utc=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
    )

    assert result is False


@pytest.mark.asyncio
async def test_reserve_post_game_prompt_returns_false_when_referrals_already_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(referral_prompt_shown_at=None)
    monkeypatch.setattr(prompt.UsersRepo, "get_by_id_for_update", _async_return(user))
    monkeypatch.setattr(prompt.QuizSessionsRepo, "count_completed_for_user", _async_return(1))
    monkeypatch.setattr(prompt.ReferralsRepo, "count_for_referrer", _async_return(2))

    result = await prompt.reserve_post_game_prompt(
        AsyncSessionStub(),
        user_id=7,
        now_utc=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
    )

    assert result is False


@pytest.mark.asyncio
@pytest.mark.parametrize("completed_sessions", [1, 2])
async def test_reserve_post_game_prompt_sets_timestamp_for_eligible_user(
    monkeypatch: pytest.MonkeyPatch,
    completed_sessions: int,
) -> None:
    now_utc = datetime(2026, 2, 20, 12, 0, tzinfo=UTC)
    user = SimpleNamespace(referral_prompt_shown_at=None)
    monkeypatch.setattr(prompt.UsersRepo, "get_by_id_for_update", _async_return(user))
    monkeypatch.setattr(
        prompt.QuizSessionsRepo,
        "count_completed_for_user",
        _async_return(completed_sessions),
    )
    monkeypatch.setattr(prompt.ReferralsRepo, "count_for_referrer", _async_return(0))

    result = await prompt.reserve_post_game_prompt(AsyncSessionStub(), user_id=7, now_utc=now_utc)

    assert result is True
    assert user.referral_prompt_shown_at == now_utc
