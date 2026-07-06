import pytest

from app.bot.handlers.gameplay_flows import arena_duel_flow, arena_duel_flow_results
from app.game.arena_duels.constants import (
    ARENA_ATTEMPT_RESULT_DRAW,
    ARENA_ATTEMPT_RESULT_LOSS,
    ARENA_ATTEMPT_RESULT_WIN,
)
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

CLOSE_LOSS_CALLBACKS = [
    f"arena:revanche:{OPPONENT_ATTEMPT_ID}",
    "buy:FRIEND_CHALLENGE_5:duel:close_loss",
    "buy:PREMIUM_WEEK:duel:close_loss",
    "arena:list",
]


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

    text = require_text(callback.message.answers[0].text)
    assert "Knapp verloren." in text
    assert "Nur 4 Sekunden Unterschied." in text
    assert "Willst du sofort eine Revanche?" in text
    assert callback_data_list(callback.message.answers[0].kwargs["reply_markup"]) == (
        CLOSE_LOSS_CALLBACKS
    )


@pytest.mark.asyncio
async def test_arena_completion_one_answer_loss_result_has_revanche() -> None:
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
            attempt_id=OPPONENT_ATTEMPT_ID,
        ),
    )

    await arena_duel_flow.send_arena_completion_result(
        callback,
        completion=completion,
        session_local=SessionLocalStub(),
        user_onboarding_service=UserServiceStub(),
    )

    response = callback.message.answers[0]
    text = require_text(response.text)
    assert "Max bleibt vorne." in text
    assert "Nur 1 Antwort Unterschied." in text
    assert "Willst du sofort eine Revanche?" in text
    assert callback_data_list(response.kwargs["reply_markup"]) == CLOSE_LOSS_CALLBACKS


def test_close_loss_accepts_equal_score_time_loss_within_limit() -> None:
    assert arena_duel_flow_results._is_close_loss(
        completed_attempt=_attempt_result_line(
            score=6,
            time_ms=63_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
        ),
        opponent_attempt=_attempt_result_line(
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
    )


def test_close_loss_rejects_equal_score_time_loss_above_limit() -> None:
    assert not arena_duel_flow_results._is_close_loss(
        completed_attempt=_attempt_result_line(
            score=6,
            time_ms=63_001,
            result=ARENA_ATTEMPT_RESULT_LOSS,
        ),
        opponent_attempt=_attempt_result_line(
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
    )


def test_close_loss_rejects_equal_score_when_player_was_not_slower() -> None:
    assert not arena_duel_flow_results._is_close_loss(
        completed_attempt=_attempt_result_line(
            score=6,
            time_ms=47_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
        ),
        opponent_attempt=_attempt_result_line(
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
    )


def test_close_loss_accepts_one_answer_gap_from_minimum_score() -> None:
    assert arena_duel_flow_results._is_close_loss(
        completed_attempt=_attempt_result_line(
            score=4,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
        ),
        opponent_attempt=_attempt_result_line(
            score=5,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
    )


def test_close_loss_rejects_one_answer_gap_below_minimum_score() -> None:
    assert not arena_duel_flow_results._is_close_loss(
        completed_attempt=_attempt_result_line(
            score=1,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
        ),
        opponent_attempt=_attempt_result_line(
            score=2,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
    )


def test_close_loss_rejects_two_answer_gap() -> None:
    assert not arena_duel_flow_results._is_close_loss(
        completed_attempt=_attempt_result_line(
            score=4,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
        ),
        opponent_attempt=_attempt_result_line(
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
    )


def test_close_loss_rejects_wins() -> None:
    assert not arena_duel_flow_results._is_close_loss(
        completed_attempt=_attempt_result_line(
            score=6,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_WIN,
        ),
        opponent_attempt=_attempt_result_line(
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_LOSS,
        ),
    )


def test_close_loss_rejects_draws() -> None:
    assert not arena_duel_flow_results._is_close_loss(
        completed_attempt=_attempt_result_line(
            score=6,
            time_ms=52_000,
            result=ARENA_ATTEMPT_RESULT_DRAW,
        ),
        opponent_attempt=_attempt_result_line(
            score=6,
            time_ms=48_000,
            result=ARENA_ATTEMPT_RESULT_DRAW,
        ),
    )


def _attempt_result_line(
    *,
    score: int,
    time_ms: int,
    result: str,
) -> ArenaAttemptResultLine:
    return ArenaAttemptResultLine(
        user_id=101,
        score=score,
        time_ms=time_ms,
        result=result,
    )
