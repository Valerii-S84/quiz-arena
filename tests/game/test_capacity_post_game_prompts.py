from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from app.bot.handlers.gameplay_flows import answer_delivery
from app.economy.referrals.service import prompt
from app.game.sessions.types import AnswerSessionResult
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 6, 18, 12, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_referral_prompt_uses_capped_completed_session_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncSessionStub()
    user = SimpleNamespace(referral_prompt_shown_at=None)
    captured: dict[str, object] = {}

    monkeypatch.setattr(prompt.UsersRepo, "get_by_id_for_update", _async_return(user))
    monkeypatch.setattr(prompt.ReferralsRepo, "count_for_referrer", _async_return(0))

    async def _count_completed(session, *, user_id: int, cap: int | None = None):
        captured["count"] = (session, user_id, cap)
        return 2

    monkeypatch.setattr(prompt.QuizSessionsRepo, "count_completed_for_user", _count_completed)

    result = await prompt.reserve_post_game_prompt(
        session,
        user_id=11,
        now_utc=NOW_UTC,
    )

    assert result is True
    assert user.referral_prompt_shown_at == NOW_UTC
    assert captured["count"] == (session, 11, 3)


@pytest.mark.asyncio
async def test_prompt_resolution_skips_non_menu_sources_without_prompt_work() -> None:
    async def _unexpected_prompt_work(*_args, **_kwargs):
        pytest.fail("friend challenge answers should not run post-game prompt work")

    state = await answer_delivery.resolve_post_game_prompts(
        AsyncSessionStub(),
        user_id=11,
        result=AnswerSessionResult(
            session_id=uuid4(),
            question_id="q-friend",
            is_correct=True,
            current_streak=1,
            best_streak=3,
            idempotent_replay=False,
            mode_code="QUICK_MIX_A1A2",
            source="FRIEND_CHALLENGE",
        ),
        request=cast(Any, SimpleNamespace(now_utc=NOW_UTC)),
        context=cast(
            Any,
            SimpleNamespace(
                services=SimpleNamespace(
                    referral_service=SimpleNamespace(
                        reserve_post_game_prompt=_unexpected_prompt_work,
                    ),
                ),
            ),
        ),
    )

    assert state.show_referral is False


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
