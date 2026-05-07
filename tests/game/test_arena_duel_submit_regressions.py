from __future__ import annotations

from tests.game.arena_duel_regressions_support import (
    NOW_UTC,
    TEXTS_DE,
    UUID,
    AsyncSessionStub,
    FriendChallengeAccessError,
    SimpleNamespace,
    _arena_result,
    _continue_arena,
    _return,
    _start_result,
    pytest,
    sessions_submit,
    uuid4,
)


@pytest.mark.asyncio
async def test_submit_answer_returns_arena_context(monkeypatch: pytest.MonkeyPatch) -> None:
    arena_attempt_id = uuid4()
    quiz_session = SimpleNamespace(
        id=uuid4(),
        user_id=11,
        source="ARENA_DUEL",
        status="STARTED",
        mode_code="QUICK_MIX_A1A2",
        question_id="arena-q-3",
        started_at=NOW_UTC,
        arena_attempt_id=arena_attempt_id,
        arena_round=3,
        friend_challenge_round=None,
    )
    question = SimpleNamespace(
        question_id="arena-q-3",
        correct_option=1,
        options=("A", "B", "C", "D"),
        level="A2",
    )
    monkeypatch.setattr(sessions_submit.QuizAttemptsRepo, "create", _return(None))
    monkeypatch.setattr(sessions_submit.QuizAttemptsRepo, "get_by_idempotency_key", _return(None))
    monkeypatch.setattr(
        sessions_submit.QuizSessionsRepo, "get_by_id_for_update", _return(quiz_session)
    )
    monkeypatch.setattr(sessions_submit, "_load_question_for_session", _return(question))
    monkeypatch.setattr(
        sessions_submit, "_apply_friend_challenge_answer", _return((None, False, False))
    )
    monkeypatch.setattr(
        sessions_submit.StreakService,
        "record_activity",
        _return(SimpleNamespace(current_streak=4, best_streak=8)),
    )
    monkeypatch.setattr(sessions_submit, "_is_persistent_adaptive_mode", lambda **_kw: False)

    result = await sessions_submit.submit_answer(
        AsyncSessionStub(),
        user_id=11,
        session_id=quiz_session.id,
        selected_option=1,
        idempotency_key="answer:arena",
        now_utc=NOW_UTC,
    )

    assert result.arena_attempt_id == arena_attempt_id
    assert result.arena_answered_round == 3


@pytest.mark.asyncio
async def test_continue_after_arena_answer_starts_next_round_with_context() -> None:
    captured: list[dict[str, object]] = []
    arena_attempt_id = uuid4()

    async def _start_session(*args, **kwargs):
        del args
        captured.append(kwargs)
        return _start_result()

    callback = await _continue_arena(
        _arena_result(arena_attempt_id, 2),
        _start_session,
        text="next-arena-question",
    )

    assert captured[0]["arena_attempt_id"] == arena_attempt_id
    assert captured[0]["arena_round"] == 3
    assert captured[0]["duel_limit_checked"] is True
    assert callback.message.answers[0].text == "next-arena-question"


@pytest.mark.asyncio
async def test_continue_after_arena_answer_handles_next_round_access_failure() -> None:
    async def _start_session(*_args, **_kwargs):
        raise FriendChallengeAccessError

    callback = await _continue_arena(
        _arena_result(uuid4(), 2),
        _start_session,
    )

    assert callback.message.answers == []
    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_continue_after_arena_answer_rejects_missing_attempt_context() -> None:
    async def _unexpected_start_session(*_args, **_kwargs):
        pytest.fail("invalid ARENA_DUEL continuation must not start another session")

    callback = await _continue_arena(
        _arena_result(None, 2),
        _unexpected_start_session,
    )

    assert callback.message.answers == []
    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_continue_after_final_arena_baseline_round_publishes_duel() -> None:
    arena_attempt_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    completed: list[dict[str, object]] = []

    async def _unexpected_start_session(*_args, **_kwargs):
        pytest.fail("final ARENA_DUEL round must not start another session")

    async def _complete_attempt(*args, **kwargs):
        del args
        completed.append(kwargs)
        return SimpleNamespace(beaten_notification=None)

    callback = await _continue_arena(
        _arena_result(arena_attempt_id, 7),
        _unexpected_start_session,
        complete_arena_attempt_if_applicable=_complete_attempt,
    )

    assert completed == [
        {
            "attempt_id": arena_attempt_id,
            "user_id": 101,
            "now_utc": NOW_UTC,
        }
    ]
    assert callback.message.answers == []
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
