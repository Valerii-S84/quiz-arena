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
    def __init__(self, events: list[str], bot: DummyBot, phase: int) -> None:
        self._events = events
        self._bot = bot
        self._phase = phase

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self._phase == 0:
            assert self._bot.sent_messages == []
        else:
            assert self._bot.sent_messages != []
        status = "commit" if exc_type is None else "rollback"
        self._events.append(f"{status}:{self._phase}")
        return False


class _RecordingSessionLocal:
    def __init__(self, events: list[str], bot: DummyBot) -> None:
        self._events = events
        self._bot = bot
        self._phase = 0

    def begin(self) -> _RecordingBegin:
        phase = self._phase
        self._phase += 1
        return _RecordingBegin(self._events, self._bot, phase)


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
async def test_revanche_delivery_records_sent_after_successful_push() -> None:
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
        assert bot.sent_messages != []
        events.append("record_sent")
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
    assert events == ["commit:0", "record_sent", "commit:1"]
    assert bot.sent_messages[0]["chat_id"] == 110_000_011


@pytest.mark.asyncio
async def test_revanche_delivery_does_not_record_sent_when_push_fails() -> None:
    events: list[str] = []
    bot = DummyBot()
    bot.raise_on_send_message = True
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
        pytest.fail("failed Telegram push must not record arena_revanche_sent")

    with pytest.raises(RuntimeError):
        await create_and_send_revanche(
            callback,
            session_local=_RecordingSessionLocal(events, bot),
            user_onboarding_service=_UserService,
            prepare_arena_revanche_request=_prepare,
            record_arena_revanche_sent=_record,
            source_attempt_id=SOURCE_ATTEMPT_ID,
            now_utc=NOW_UTC,
        )

    assert events == ["commit:0"]
    assert bot.sent_messages == []
