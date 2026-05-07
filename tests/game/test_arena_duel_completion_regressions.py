from __future__ import annotations

from tests.game.arena_duel_regressions_support import (
    ARENA_BEATEN_NOTIFICATION_TYPE,
    NOW_UTC,
    UUID,
    ArenaBeatenNotification,
    SimpleNamespace,
    _arena_result,
    _continue_arena,
    arena_notifications,
    pytest,
)


@pytest.mark.asyncio
async def test_continue_after_final_arena_challenger_round_does_not_publish_baseline() -> None:
    arena_attempt_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    completed: list[dict[str, object]] = []

    async def _unexpected_start_session(*_args, **_kwargs):
        pytest.fail("final ARENA_DUEL round must not start another session")

    async def _complete_if_applicable(*args, **kwargs):
        del args
        completed.append(kwargs)
        return SimpleNamespace(beaten_notification=None)

    callback = await _continue_arena(
        _arena_result(arena_attempt_id, 7),
        _unexpected_start_session,
        complete_arena_attempt_if_applicable=_complete_if_applicable,
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


@pytest.mark.asyncio
async def test_continue_after_final_arena_challenger_round_sends_beaten_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arena_attempt_id = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    notification = ArenaBeatenNotification(
        arena_duel_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        previous_best_attempt_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        previous_best_user_id=11,
        previous_best_score=6,
        previous_best_time_ms=48_000,
        new_best_attempt_id=arena_attempt_id,
        new_best_user_id=101,
        new_best_score=7,
        new_best_time_ms=52_000,
        notification_type=ARENA_BEATEN_NOTIFICATION_TYPE,
    )
    sent: list[dict[str, object]] = []

    async def _unexpected_start_session(*_args, **_kwargs):
        pytest.fail("final ARENA_DUEL round must not start another session")

    async def _complete_if_applicable(*_args, **_kwargs):
        return SimpleNamespace(beaten_notification=notification)

    async def _send_notification(**kwargs):
        sent.append(kwargs)
        return {"sent_total": 1, "failed_total": 0, "skipped_total": 0}

    monkeypatch.setattr(arena_notifications, "send_arena_beaten_notification", _send_notification)

    callback = await _continue_arena(
        _arena_result(arena_attempt_id, 7),
        _unexpected_start_session,
        complete_arena_attempt_if_applicable=_complete_if_applicable,
    )

    assert sent == [
        {
            "notification": notification,
            "happened_at": NOW_UTC,
            "bot": callback.bot,
            "source": "BOT",
        }
    ]
    assert callback.message.answers == []
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
