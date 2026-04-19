from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TypeVar, cast
from uuid import UUID

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_CREATOR_DONE
from app.workers.tasks import friend_challenges_async
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 3, 20, 10, 0, tzinfo=UTC)
CHALLENGE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
T = TypeVar("T")


def _session_local_with_sessions(*sessions: object) -> SimpleNamespace:
    remaining = list(sessions)
    return SimpleNamespace(begin=lambda: AsyncBeginContext(remaining.pop(0)))


def _challenge(**overrides: object) -> SimpleNamespace:
    payload: dict[str, object] = {
        "id": CHALLENGE_ID,
        "creator_user_id": 101,
        "opponent_user_id": 202,
        "status": "CREATOR_DONE",
        "creator_push_count": 0,
        "opponent_push_count": 0,
        "expires_last_chance_notified_at": None,
        "updated_at": None,
        "expires_at": NOW_UTC + timedelta(minutes=10),
        "creator_score": 3,
        "opponent_score": 2,
        "total_rounds": 5,
        "winner_user_id": None,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


async def _async_return(value: T) -> T:
    return value


class _FrozenDateTime:
    @staticmethod
    def now(_tz) -> datetime:
        return NOW_UTC


@pytest.mark.asyncio
async def test_run_friend_challenge_deadlines_async_queues_last_chance_and_emits_notice_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processing_session = SimpleNamespace()
    analytics_session = SimpleNamespace()
    analytics_calls: list[dict[str, object]] = []
    notification_calls: list[dict[str, object]] = []
    logged: list[dict[str, object]] = []
    challenge = _challenge(status=DUEL_STATUS_CREATOR_DONE)

    monkeypatch.setattr(friend_challenges_async, "datetime", _FrozenDateTime)
    monkeypatch.setattr(
        friend_challenges_async,
        "SessionLocal",
        _session_local_with_sessions(processing_session, analytics_session),
    )
    monkeypatch.setattr(
        friend_challenges_async.FriendChallengesRepo,
        "list_active_due_for_last_chance_for_update",
        lambda *_args, **_kwargs: _async_return([challenge]),
    )
    monkeypatch.setattr(
        friend_challenges_async.FriendChallengesRepo,
        "list_pending_due_for_expire_for_update",
        lambda *_args, **_kwargs: _async_return([]),
    )
    monkeypatch.setattr(
        friend_challenges_async.FriendChallengesRepo,
        "list_joined_due_for_walkover_for_update",
        lambda *_args, **_kwargs: _async_return([]),
    )
    monkeypatch.setattr(
        friend_challenges_async,
        "_expire_friend_challenge_if_due",
        lambda **_kwargs: False,
    )

    async def _fake_send_deadline_notifications(**kwargs):
        notification_calls.append(kwargs)
        return (1, 0, 0, 0, [{"challenge_id": str(CHALLENGE_ID), "sent_to": 1}], [])

    async def _fake_emit_analytics_event(session, **kwargs):
        analytics_calls.append({"session": session, **kwargs})

    monkeypatch.setattr(
        friend_challenges_async,
        "send_deadline_notifications",
        _fake_send_deadline_notifications,
    )
    monkeypatch.setattr(
        friend_challenges_async,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )
    monkeypatch.setattr(
        friend_challenges_async.logger,
        "info",
        lambda event, **kwargs: logged.append({"event": event, **kwargs}),
    )

    result = await friend_challenges_async.run_friend_challenge_deadlines_async(batch_size=4)

    assert result == {
        "batch_size": 4,
        "last_chance_queued_total": 1,
        "expired_total": 0,
        "last_chance_sent_total": 1,
        "last_chance_failed_total": 0,
        "expired_notice_sent_total": 0,
        "expired_notice_failed_total": 0,
    }
    assert challenge.opponent_push_count == 1
    assert challenge.expires_last_chance_notified_at == NOW_UTC
    assert challenge.updated_at == NOW_UTC
    reminder_items = cast(list[dict[str, object]], notification_calls[0]["reminder_items"])
    assert reminder_items[0]["target_user_id"] == 202
    assert notification_calls[0]["expired_items"] == []
    assert analytics_calls == [
        {
            "session": analytics_session,
            "event_type": "friend_challenge_last_chance_sent",
            "source": friend_challenges_async.EVENT_SOURCE_WORKER,
            "happened_at": NOW_UTC,
            "user_id": None,
            "payload": {"challenge_id": str(CHALLENGE_ID), "sent_to": 1},
        }
    ]
    assert logged[0]["event"] == "friend_challenge_deadlines_processed"


@pytest.mark.asyncio
async def test_run_friend_challenge_deadlines_async_collects_expired_items_and_emits_both_event_layers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processing_session = SimpleNamespace()
    analytics_session = SimpleNamespace()
    analytics_calls: list[dict[str, object]] = []
    challenge = _challenge(
        status="PENDING",
        opponent_user_id=None,
        expires_at=NOW_UTC - timedelta(minutes=1),
    )

    monkeypatch.setattr(friend_challenges_async, "datetime", _FrozenDateTime)
    monkeypatch.setattr(
        friend_challenges_async,
        "SessionLocal",
        _session_local_with_sessions(processing_session, analytics_session),
    )
    monkeypatch.setattr(
        friend_challenges_async.FriendChallengesRepo,
        "list_active_due_for_last_chance_for_update",
        lambda *_args, **_kwargs: _async_return([]),
    )
    monkeypatch.setattr(
        friend_challenges_async.FriendChallengesRepo,
        "list_pending_due_for_expire_for_update",
        lambda *_args, **_kwargs: _async_return([challenge]),
    )
    monkeypatch.setattr(
        friend_challenges_async.FriendChallengesRepo,
        "list_joined_due_for_walkover_for_update",
        lambda *_args, **_kwargs: _async_return([]),
    )

    def _fake_expire_friend_challenge_if_due(*, challenge, now_utc) -> bool:
        assert now_utc == NOW_UTC
        challenge.status = "EXPIRED"
        return True

    async def _fake_send_deadline_notifications(**kwargs):
        assert kwargs["reminder_items"] == []
        return (
            0,
            0,
            1,
            0,
            [],
            [{"challenge_id": str(CHALLENGE_ID), "status": "EXPIRED"}],
        )

    async def _fake_emit_analytics_event(session, **kwargs):
        analytics_calls.append({"session": session, **kwargs})

    monkeypatch.setattr(
        friend_challenges_async,
        "_expire_friend_challenge_if_due",
        _fake_expire_friend_challenge_if_due,
    )
    monkeypatch.setattr(
        friend_challenges_async,
        "send_deadline_notifications",
        _fake_send_deadline_notifications,
    )
    monkeypatch.setattr(
        friend_challenges_async,
        "emit_analytics_event",
        _fake_emit_analytics_event,
    )
    monkeypatch.setattr(friend_challenges_async.logger, "info", lambda *_args, **_kwargs: None)

    result = await friend_challenges_async.run_friend_challenge_deadlines_async(batch_size=3)

    assert result == {
        "batch_size": 3,
        "last_chance_queued_total": 0,
        "expired_total": 1,
        "last_chance_sent_total": 0,
        "last_chance_failed_total": 0,
        "expired_notice_sent_total": 1,
        "expired_notice_failed_total": 0,
    }
    assert analytics_calls[0] == {
        "session": processing_session,
        "event_type": "duel_expired",
        "source": friend_challenges_async.EVENT_SOURCE_WORKER,
        "happened_at": NOW_UTC,
        "user_id": None,
        "payload": {
            "challenge_id": str(CHALLENGE_ID),
            "creator_user_id": 101,
            "opponent_user_id": None,
            "creator_score": 3,
            "opponent_score": 2,
            "total_rounds": 5,
            "winner_user_id": None,
            "status": "EXPIRED",
            "previous_status": "PENDING",
            "expires_at": challenge.expires_at.isoformat(),
        },
    }
    assert analytics_calls[1] == {
        "session": analytics_session,
        "event_type": "friend_challenge_expired_notice_sent",
        "source": friend_challenges_async.EVENT_SOURCE_WORKER,
        "happened_at": NOW_UTC,
        "user_id": None,
        "payload": {"challenge_id": str(CHALLENGE_ID), "status": "EXPIRED"},
    }
