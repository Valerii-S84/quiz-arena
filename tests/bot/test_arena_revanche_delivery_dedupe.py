from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows import arena_revanche_delivery
from tests.bot.helpers import DummyBot, DummyCallback, DummyMessage

SOURCE_ATTEMPT_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
CHALLENGE_ID = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
NOW_UTC = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)


class _RecordingBegin:
    def __init__(self, events: list[str], phase: int) -> None:
        self._events = events
        self._phase = phase

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        status = "commit" if exc_type is None else "rollback"
        self._events.append(f"{status}:{self._phase}")
        return False


class _RecordingSessionLocal:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self._phase = 0

    def begin(self) -> _RecordingBegin:
        phase = self._phase
        self._phase += 1
        return _RecordingBegin(self._events, phase)


class _UserService:
    @staticmethod
    async def ensure_home_snapshot(*_args, **_kwargs):
        return SimpleNamespace(user_id=101)

    @staticmethod
    async def get_by_id(_session, user_id: int):
        if user_id == 11:
            return SimpleNamespace(
                id=11,
                telegram_user_id=110_000_011,
                username=None,
                first_name="Max",
            )
        if user_id == 101:
            return SimpleNamespace(
                id=101,
                telegram_user_id=101_000_101,
                username="anna",
                first_name="Anna",
            )
        return None


@pytest.mark.asyncio
async def test_revanche_delivery_skips_push_when_sent_marker_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    bot = DummyBot()
    callback = DummyCallback(
        data=f"arena:revanche_send:{SOURCE_ATTEMPT_ID}",
        from_user=SimpleNamespace(id=777),
        message=DummyMessage(bot=bot),
    )

    async def _prepare(*_args, **_kwargs):
        return SimpleNamespace(
            already_sent=False,
            context=SimpleNamespace(receiver_user_id=11),
            challenge=SimpleNamespace(challenge_id=CHALLENGE_ID),
        )

    async def _lock(*_args, **_kwargs):
        events.append("lock")

    async def _is_sent(*_args, **_kwargs):
        return True

    async def _record(*_args, **_kwargs):
        pytest.fail("existing sent marker must skip duplicate push")

    async def _cleanup(*_args, **_kwargs):
        pytest.fail("existing sent marker must not cleanup Revanche state")

    monkeypatch.setattr(arena_revanche_delivery, "lock_arena_revanche_delivery", _lock)
    monkeypatch.setattr(arena_revanche_delivery, "is_arena_revanche_sent", _is_sent)

    opponent_label = await arena_revanche_delivery.create_and_send_revanche(
        callback,
        session_local=_RecordingSessionLocal(events),
        user_onboarding_service=_UserService,
        prepare_arena_revanche_request=_prepare,
        record_arena_revanche_sent=_record,
        cleanup_arena_revanche_request=_cleanup,
        source_attempt_id=SOURCE_ATTEMPT_ID,
        now_utc=NOW_UTC,
    )

    assert opponent_label == "Max"
    assert events == ["lock", "commit:0"]
    assert bot.sent_messages == []
