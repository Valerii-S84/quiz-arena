from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import app.economy.referrals.service.prompt as referral_prompt
from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_reserve_post_game_prompt_marks_user_on_third_completed_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(referral_prompt_shown_at=None)
    now_utc = datetime.now(UTC)

    async def _fake_get_by_id_for_update(_session, user_id: int):
        assert user_id == 17
        return user

    async def _fake_count_completed_for_user(_session, *, user_id: int):
        assert user_id == 17
        return 3

    async def _fake_count_for_referrer(_session, *, referrer_user_id: int):
        assert referrer_user_id == 17
        return 0

    monkeypatch.setattr(
        referral_prompt.UsersRepo, "get_by_id_for_update", _fake_get_by_id_for_update
    )
    monkeypatch.setattr(
        referral_prompt.QuizSessionsRepo,
        "count_completed_for_user",
        _fake_count_completed_for_user,
    )
    monkeypatch.setattr(
        referral_prompt.ReferralsRepo,
        "count_for_referrer",
        _fake_count_for_referrer,
    )

    reserved = await referral_prompt.reserve_post_game_prompt(
        _Session(),
        user_id=17,
        now_utc=now_utc,
    )

    assert reserved is True
    assert user.referral_prompt_shown_at == now_utc


@pytest.mark.asyncio
async def test_reserve_post_game_prompt_skips_second_completed_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get_by_id_for_update(_session, user_id: int):
        assert user_id == 17
        return SimpleNamespace(referral_prompt_shown_at=None)

    async def _fake_count_completed_for_user(_session, *, user_id: int):
        assert user_id == 17
        return 2

    async def _fake_count_for_referrer(*_args, **_kwargs):
        raise AssertionError("referrals must not be checked before the session threshold")

    monkeypatch.setattr(
        referral_prompt.UsersRepo, "get_by_id_for_update", _fake_get_by_id_for_update
    )
    monkeypatch.setattr(
        referral_prompt.QuizSessionsRepo,
        "count_completed_for_user",
        _fake_count_completed_for_user,
    )
    monkeypatch.setattr(
        referral_prompt.ReferralsRepo,
        "count_for_referrer",
        _fake_count_for_referrer,
    )

    reserved = await referral_prompt.reserve_post_game_prompt(
        _Session(),
        user_id=17,
        now_utc=datetime.now(UTC),
    )

    assert reserved is False
