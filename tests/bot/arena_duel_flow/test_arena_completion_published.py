import pytest

from app.bot.handlers.gameplay_flows import arena_duel_flow
from app.game.arena_duels.types import ArenaAttemptCompletionResult, ArenaAttemptResultLine

from .support import (
    DUEL_ID,
    SessionLocalStub,
    UserServiceStub,
    callback_data_list,
    duel_snapshot,
    make_callback,
    require_text,
)


@pytest.mark.asyncio
async def test_arena_completion_published_result_screen() -> None:
    callback = make_callback("answer")
    completion = ArenaAttemptCompletionResult(
        duel=duel_snapshot(),
        completed_attempt=ArenaAttemptResultLine(
            user_id=101,
            score=6,
            time_ms=48_000,
            result="BASELINE",
        ),
    )

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
    )

    response = callback.message.answers[0]
    text = require_text(response.text)
    assert "Dein Arena-Duell ist aktiv!" in text
    assert "6/7 · 00:48" in text
    assert callback_data_list(response.kwargs["reply_markup"]) == [
        f"arena:challenge_friend:{DUEL_ID}",
        "arena:list",
    ]


@pytest.mark.asyncio
async def test_arena_completion_published_result_offers_same_duel_friend_challenge() -> None:
    callback = make_callback("answer")
    completion = ArenaAttemptCompletionResult(
        duel=duel_snapshot(),
        completed_attempt=ArenaAttemptResultLine(
            user_id=101,
            score=6,
            time_ms=48_000,
            result="BASELINE",
        ),
    )

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
    )

    callbacks = callback_data_list(callback.message.answers[0].kwargs["reply_markup"])
    assert f"arena:challenge_friend:{DUEL_ID}" in callbacks
    assert "duels:friend" not in callbacks


@pytest.mark.asyncio
async def test_arena_completion_without_completed_attempt_is_silent() -> None:
    callback = make_callback("answer")
    completion = ArenaAttemptCompletionResult(duel=duel_snapshot())

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
    )

    assert callback.message.answers == []
