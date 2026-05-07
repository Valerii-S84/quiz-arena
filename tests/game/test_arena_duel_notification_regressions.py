from __future__ import annotations

from tests.game.arena_duel_regressions_support import (
    ARENA_BEATEN_NOTIFICATION_TYPE,
    NOW_UTC,
    UUID,
    ArenaBeatenNotification,
    SimpleNamespace,
    _arena_result,
    _callback,
    _continue_arena,
    arena_notifications,
    play_flow,
    pytest,
)


@pytest.mark.asyncio
async def test_continue_after_final_arena_challenger_round_acknowledges_before_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arena_attempt_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
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
    callback = _callback()
    sent: list[dict[str, object]] = []

    async def _unexpected_start_session(*_args, **_kwargs):
        pytest.fail("final ARENA_DUEL round must not start another session")

    async def _complete_if_applicable(*_args, **_kwargs):
        return SimpleNamespace(beaten_notification=notification)

    async def _send_notification(**kwargs):
        assert callback.answer_calls == [{"text": None, "show_alert": False}]
        sent.append(kwargs)
        return {"sent_total": 1, "failed_total": 0, "skipped_total": 0}

    monkeypatch.setattr(arena_notifications, "send_arena_beaten_notification", _send_notification)

    callback = await _continue_arena(
        _arena_result(arena_attempt_id, 7),
        _unexpected_start_session,
        complete_arena_attempt_if_applicable=_complete_if_applicable,
        callback=callback,
    )

    assert sent == [
        {
            "notification": notification,
            "happened_at": NOW_UTC,
            "bot": callback.bot,
            "source": "BOT",
        }
    ]
    assert callback.answer_calls == [{"text": None, "show_alert": False}]


@pytest.mark.asyncio
async def test_continue_after_final_arena_challenger_round_keeps_notification_best_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arena_attempt_id = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
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
    warnings: list[dict[str, object]] = []

    async def _unexpected_start_session(*_args, **_kwargs):
        pytest.fail("final ARENA_DUEL round must not start another session")

    async def _complete_if_applicable(*_args, **_kwargs):
        return SimpleNamespace(beaten_notification=notification)

    async def _failing_send_notification(**_kwargs):
        raise RuntimeError("notification backend unavailable")

    def _warning(event: str, **kwargs) -> None:
        warnings.append({"event": event, **kwargs})

    monkeypatch.setattr(
        arena_notifications, "send_arena_beaten_notification", _failing_send_notification
    )
    monkeypatch.setattr(play_flow, "logger", SimpleNamespace(warning=_warning))

    callback = await _continue_arena(
        _arena_result(arena_attempt_id, 7),
        _unexpected_start_session,
        complete_arena_attempt_if_applicable=_complete_if_applicable,
    )

    assert callback.message.answers == []
    assert callback.answer_calls == [{"text": None, "show_alert": False}]
    assert warnings == [
        {
            "event": "arena_beaten_notification_failed",
            "arena_duel_id": str(notification.arena_duel_id),
            "previous_best_attempt_id": str(notification.previous_best_attempt_id),
            "new_best_attempt_id": str(notification.new_best_attempt_id),
            "error_type": "RuntimeError",
        }
    ]
