from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

from app.game.arena_duels.constants import ARENA_DUEL_STATUS_ACTIVE, ARENA_SOURCE
from app.game.arena_duels.types import ArenaActiveDuelSnapshot, ArenaDuelSnapshot
from app.game.sessions.types import SessionQuestionView, StartSessionResult
from tests.bot.helpers import DummyCallback, DummyMessage
from tests.type_helpers import AsyncBeginContext

NOW_UTC = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)
DUEL_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ATTEMPT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
OPPONENT_ATTEMPT_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
SESSION_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


class SessionLocalStub:
    def begin(self) -> AsyncBeginContext[object]:
        return AsyncBeginContext(object())


class UserServiceStub:
    @staticmethod
    async def ensure_home_snapshot(*_args, **_kwargs):
        return SimpleNamespace(user_id=101, free_energy=8, paid_energy=2)

    @staticmethod
    async def get_by_id(_session, user_id: int):
        if user_id == 11:
            return SimpleNamespace(username=None, first_name="Max")
        return None


class UserServiceWithTelegramStub:
    @staticmethod
    async def ensure_home_snapshot(*_args, **_kwargs):
        return SimpleNamespace(user_id=101, free_energy=8, paid_energy=2)

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


def active_duel() -> ArenaActiveDuelSnapshot:
    return ArenaActiveDuelSnapshot(
        duel_id=DUEL_ID,
        creator_user_id=11,
        mode_code="QUICK_MIX_A1A2",
        question_ids=tuple(f"q-{index}" for index in range(1, 8)),
        baseline_attempt_id=ATTEMPT_ID,
        score=6,
        time_ms=48_000,
        expires_at=NOW_UTC + timedelta(hours=1),
    )


def duel_snapshot() -> ArenaDuelSnapshot:
    return ArenaDuelSnapshot(
        duel_id=DUEL_ID,
        creator_user_id=101,
        mode_code="QUICK_MIX_A1A2",
        status=ARENA_DUEL_STATUS_ACTIVE,
        question_ids=tuple(f"q-{index}" for index in range(1, 8)),
        expires_at=NOW_UTC + timedelta(hours=24),
        created_at=NOW_UTC,
        updated_at=NOW_UTC,
        baseline_attempt_id=ATTEMPT_ID,
        baseline_score=6,
        baseline_time_ms=48_000,
    )


def start_result() -> StartSessionResult:
    return StartSessionResult(
        session=SessionQuestionView(
            session_id=SESSION_ID,
            question_id="q-1",
            text="Frage?",
            options=("A", "B", "C", "D"),
            mode_code="QUICK_MIX_A1A2",
            source=ARENA_SOURCE,
            question_number=1,
            total_questions=7,
        ),
        energy_free=0,
        energy_paid=0,
        idempotent_replay=False,
    )


def make_callback(data: str) -> DummyCallback:
    return DummyCallback(
        data=data,
        from_user=SimpleNamespace(id=777),
        message=DummyMessage(),
    )


def callback_data_list(reply_markup) -> list[str]:
    return [
        button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


def require_text(value: str | None) -> str:
    assert value is not None
    return value
