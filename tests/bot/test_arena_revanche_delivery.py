from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows.arena_revanche_delivery import create_and_send_revanche
from tests.bot.helpers import DummyBot, DummyCallback, DummyMessage

SOURCE_ATTEMPT_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
CHALLENGE_ID = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
NOW_UTC = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)


class _RecordingBegin:
    def __init__(self, events: list[str], bot: DummyBot) -> None:
        self._events = events
        self._bot = bot

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        assert self._bot.sent_messages == []
        self._events.append("commit" if exc_type is None else "rollback")
        return False


class _RecordingSessionLocal:
    def __init__(self, events: list[str], bot: DummyBot) -> None:
        self._events = events
        self._bot = bot

    def begin(self) -> _RecordingBegin:
        return _RecordingBegin(self._events, self._bot)


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
async def test_revanche_delivery_commits_before_push() -> None:
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

    async def _record(*_args, **_kwargs):
        assert bot.sent_messages == []
        events.append("record")
        return True

    opponent_label = await create_and_send_revanche(
        callback,
        session_local=_RecordingSessionLocal(events, bot),
        user_onboarding_service=_UserService,
        prepare_arena_revanche_request=_prepare,
        record_arena_revanche_sent=_record,
        source_attempt_id=SOURCE_ATTEMPT_ID,
        now_utc=NOW_UTC,
    )

    assert opponent_label == "Max"
    assert events == ["record", "commit"]
    assert bot.sent_messages[0]["chat_id"] == 110_000_011


@pytest.mark.asyncio
async def test_revanche_delivery_rolls_back_lost_dedupe_race() -> None:
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

    async def _record(*_args, **_kwargs):
        events.append("record")
        return False

    opponent_label = await create_and_send_revanche(
        callback,
        session_local=_RecordingSessionLocal(events, bot),
        user_onboarding_service=_UserService,
        prepare_arena_revanche_request=_prepare,
        record_arena_revanche_sent=_record,
        source_attempt_id=SOURCE_ATTEMPT_ID,
        now_utc=NOW_UTC,
    )

    assert opponent_label == "Max"
    assert events == ["record", "rollback"]
    assert bot.sent_messages == []
