import pytest

from app.bot.handlers.gameplay_flows import arena_duel_flow
from app.game.arena_duels.constants import ARENA_ATTEMPT_RESULT_LOSS, ARENA_ATTEMPT_RESULT_WIN
from app.game.arena_duels.types import ArenaAttemptCompletionResult, ArenaAttemptResultLine

from .support import (
    OPPONENT_ATTEMPT_ID,
    SessionLocalStub,
    UserServiceStub,
    callback_data_list,
    duel_snapshot,
    make_callback,
    require_text,
)


@pytest.mark.asyncio
async def test_arena_completion_challenger_result_screen() -> None:
    callback = make_callback("answer")
    completion = ArenaAttemptCompletionResult(
        duel=duel_snapshot(),
        completed_attempt=ArenaAttemptResultLine(
            user_id=101,
            score=7,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
        opponent_attempt=ArenaAttemptResultLine(
            user_id=11,
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
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
    assert "🎉 Gewonnen!" in text
    assert "Du hast das Ergebnis von Max geschlagen." in text
    assert "7/7 · 00:52" in text
    assert "6/7 · 00:48" in text
    assert callback_data_list(response.kwargs["reply_markup"]) == ["arena:create", "arena:list"]


@pytest.mark.asyncio
async def test_arena_completion_challenger_win_result_has_revanche() -> None:
    callback = make_callback("answer")
    completion = ArenaAttemptCompletionResult(
        duel=duel_snapshot(),
        completed_attempt=ArenaAttemptResultLine(
            user_id=101,
            score=7,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
        opponent_attempt=ArenaAttemptResultLine(
            user_id=11,
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
            attempt_id=OPPONENT_ATTEMPT_ID,
        ),
    )

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
    )

    assert callback_data_list(callback.message.answers[0].kwargs["reply_markup"]) == [
        f"arena:revanche:{OPPONENT_ATTEMPT_ID}",
        "arena:list",
    ]


@pytest.mark.asyncio
async def test_arena_completion_challenger_loss_result_has_next_actions() -> None:
    callback = make_callback("answer")
    completion = ArenaAttemptCompletionResult(
        duel=duel_snapshot(),
        completed_attempt=ArenaAttemptResultLine(
            user_id=101,
            score=5,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
        ),
        opponent_attempt=ArenaAttemptResultLine(
            user_id=11,
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
    )

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
    )

    response = callback.message.answers[0]
    assert "Max bleibt vorne." in require_text(response.text)
    assert callback_data_list(response.kwargs["reply_markup"]) == ["arena:create", "arena:list"]


@pytest.mark.asyncio
async def test_arena_completion_close_loss_result_has_revanche() -> None:
    callback = make_callback("answer")
    completion = ArenaAttemptCompletionResult(
        duel=duel_snapshot(),
        completed_attempt=ArenaAttemptResultLine(
            user_id=101,
            score=6,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
        ),
        opponent_attempt=ArenaAttemptResultLine(
            user_id=11,
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
            attempt_id=OPPONENT_ATTEMPT_ID,
        ),
    )

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub,
    )

    assert "Knapp verloren." in require_text(callback.message.answers[0].text)
    assert callback_data_list(callback.message.answers[0].kwargs["reply_markup"]) == [
        f"arena:revanche:{OPPONENT_ATTEMPT_ID}",
        "buy:FRIEND_CHALLENGE_5:duel",
        "buy:PREMIUM_WEEK:duel",
        "arena:list",
    ]
