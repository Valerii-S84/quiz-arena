from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Table

from app.bot.handlers.gameplay_flows import play_flow
from app.bot.texts.de import TEXTS_DE
from app.db.models.analytics_events import AnalyticsEvent
from app.db.models.arena_duels import ArenaDuel
from app.game.arena_duels.constants import ARENA_BEATEN_NOTIFICATION_TYPE
from app.game.arena_duels.types import ArenaBeatenNotification
from app.game.sessions.errors import FriendChallengeAccessError
from app.game.sessions.service import sessions_submit
from app.game.sessions.types import AnswerSessionResult
from app.workers.tasks import arena_duels as arena_notifications
from tests.bot.gameplay_flow_fixtures import _start_result
from tests.bot.helpers import DummyCallback, DummyMessage
from tests.type_helpers import AsyncBeginContext, AsyncSessionStub

NOW_UTC = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)


class _SessionLocal:
    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(object())


def _callback() -> DummyCallback:
    return DummyCallback(data="play", from_user=SimpleNamespace(id=101), message=DummyMessage())


async def _ensure_home_snapshot(*_args, **_kwargs):
    return SimpleNamespace(user_id=101, free_energy=18, paid_energy=2)


def _arena_result(attempt_id: UUID | None, answered_round: int | None) -> AnswerSessionResult:
    return AnswerSessionResult(
        session_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        question_id="arena-q",
        is_correct=True,
        current_streak=3,
        best_streak=5,
        idempotent_replay=False,
        mode_code="QUICK_MIX_A1A2",
        source="ARENA_DUEL",
        arena_attempt_id=attempt_id,
        arena_answered_round=answered_round,
    )


async def _continue_arena(
    result: AnswerSessionResult,
    start_session,
    text: str = "unused",
    complete_arena_attempt_if_applicable=None,
    callback: DummyCallback | None = None,
):
    async def _default_complete_attempt(*_args, **_kwargs):
        pytest.fail("Arena attempt finalization was not expected")

    callback = callback or _callback()
    await play_flow.continue_regular_mode_after_answer(
        callback,
        result=result,
        now_utc=NOW_UTC,
        session_local=_SessionLocal(),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_ensure_home_snapshot),
        game_session_service=SimpleNamespace(
            start_session=start_session,
            complete_arena_attempt_if_applicable=(
                complete_arena_attempt_if_applicable or _default_complete_attempt
            ),
        ),
        offer_service=SimpleNamespace(),
        offer_logging_error=RuntimeError,
        channel_bonus_service=SimpleNamespace(),
        build_question_text=lambda **_kw: text,
    )
    return callback


def _return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


__all__ = [
    "ARENA_BEATEN_NOTIFICATION_TYPE",
    "AnalyticsEvent",
    "AnswerSessionResult",
    "ArenaBeatenNotification",
    "ArenaDuel",
    "AsyncBeginContext",
    "AsyncSessionStub",
    "DummyCallback",
    "DummyMessage",
    "FriendChallengeAccessError",
    "NOW_UTC",
    "Path",
    "SimpleNamespace",
    "TEXTS_DE",
    "Table",
    "UTC",
    "UUID",
    "_SessionLocal",
    "_arena_result",
    "_callback",
    "_continue_arena",
    "_ensure_home_snapshot",
    "_return",
    "_start_result",
    "arena_notifications",
    "cast",
    "datetime",
    "play_flow",
    "pytest",
    "sessions_submit",
    "uuid4",
]
