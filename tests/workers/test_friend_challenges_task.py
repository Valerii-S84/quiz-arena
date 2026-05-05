from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_CREATOR_DONE
from app.game.sessions.service.constants import DUEL_MAX_PUSH_PER_USER
from app.workers.tasks import friend_challenges, friend_challenges_async
from tests.type_helpers import AsyncBeginContext, build_friend_challenge

NOW_UTC = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)


class _SessionLocal:
    def __init__(self, *sessions: object) -> None:
        self._sessions = list(sessions)

    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(self._sessions.pop(0))


def test_run_friend_challenge_deadlines_task_wrapper(monkeypatch) -> None:
    async def fake_async(*, batch_size: int) -> dict[str, int]:
        return {
            "batch_size": batch_size,
            "last_chance_queued_total": 2,
            "expired_total": 1,
            "last_chance_sent_total": 2,
            "last_chance_failed_total": 0,
            "expired_notice_sent_total": 2,
            "expired_notice_failed_total": 0,
        }

    monkeypatch.setattr(friend_challenges, "run_friend_challenge_deadlines_async", fake_async)

    result = friend_challenges.run_friend_challenge_deadlines(batch_size=7)
    assert result["batch_size"] == 7
    assert result["last_chance_queued_total"] == 2


def test_format_remaining_hhmm_clamps_negative_values() -> None:
    hours, minutes = friend_challenges._format_remaining_hhmm(
        now_utc=NOW_UTC,
        expires_at=NOW_UTC - timedelta(minutes=5),
    )
    assert (hours, minutes) == (0, 0)


@pytest.mark.asyncio
async def test_run_friend_challenge_deadlines_async_queues_only_eligible_last_chance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eligible = build_friend_challenge(
        status=DUEL_STATUS_CREATOR_DONE,
        creator_user_id=11,
        opponent_user_id=22,
        opponent_push_count=0,
        expires_last_chance_notified_at=None,
        expires_at=NOW_UTC + timedelta(minutes=20),
    )
    capped = build_friend_challenge(
        status=DUEL_STATUS_CREATOR_DONE,
        creator_user_id=12,
        opponent_user_id=23,
        opponent_push_count=DUEL_MAX_PUSH_PER_USER,
        expires_last_chance_notified_at=None,
        expires_at=NOW_UTC + timedelta(minutes=15),
    )
    captured: dict[str, object] = {}

    async def _fake_last_chance(*_args, **_kwargs):
        return [eligible, capped]

    async def _fake_none(*_args, **_kwargs):
        return []

    async def _fake_send_deadline_notifications(*, now_utc, reminder_items, expired_items):
        captured["now_utc"] = now_utc
        captured["reminder_items"] = reminder_items
        captured["expired_items"] = expired_items
        return (len(reminder_items), 0, 0, 0, [], [])

    monkeypatch.setattr(friend_challenges_async, "SessionLocal", _SessionLocal(object()))
    monkeypatch.setattr(
        friend_challenges_async.FriendChallengesRepo,
        "list_active_due_for_last_chance_for_update",
        _fake_last_chance,
    )
    monkeypatch.setattr(
        friend_challenges_async.FriendChallengesRepo,
        "list_pending_due_for_expire_for_update",
        _fake_none,
    )
    monkeypatch.setattr(
        friend_challenges_async.FriendChallengesRepo,
        "list_joined_due_for_walkover_for_update",
        _fake_none,
    )
    monkeypatch.setattr(
        friend_challenges_async,
        "send_deadline_notifications",
        _fake_send_deadline_notifications,
    )

    result = await friend_challenges_async.run_friend_challenge_deadlines_async(batch_size=5)

    assert result == {
        "batch_size": 5,
        "last_chance_queued_total": 1,
        "expired_total": 0,
        "last_chance_sent_total": 1,
        "last_chance_failed_total": 0,
        "expired_notice_sent_total": 0,
        "expired_notice_failed_total": 0,
    }
    captured_now = captured["now_utc"]
    assert isinstance(captured_now, datetime)
    assert captured["expired_items"] == []
    assert captured["reminder_items"] == [
        {
            "challenge_id": str(eligible.id),
            "target_user_id": 22,
            "creator_user_id": 11,
            "opponent_user_id": 22,
            "status": DUEL_STATUS_CREATOR_DONE,
            "expires_at": eligible.expires_at,
        }
    ]
    assert eligible.opponent_push_count == 1
    assert eligible.expires_last_chance_notified_at == captured_now
    assert eligible.updated_at == captured_now
    assert capped.opponent_push_count == DUEL_MAX_PUSH_PER_USER
    assert capped.expires_last_chance_notified_at is None
