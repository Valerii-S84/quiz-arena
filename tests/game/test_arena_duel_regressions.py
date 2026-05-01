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
from app.db.models.arena_duels import ArenaDuel
from app.game.sessions.service import sessions_submit
from app.game.sessions.types import AnswerSessionResult
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
    complete_arena_creator_baseline_if_applicable=None,
):
    async def _default_complete_baseline(*_args, **_kwargs):
        pytest.fail("Arena baseline finalization was not expected")

    callback = _callback()
    await play_flow.continue_regular_mode_after_answer(
        callback,
        result=result,
        now_utc=NOW_UTC,
        session_local=_SessionLocal(),
        user_onboarding_service=SimpleNamespace(ensure_home_snapshot=_ensure_home_snapshot),
        game_session_service=SimpleNamespace(
            start_session=start_session,
            complete_arena_creator_baseline_if_applicable=(
                complete_arena_creator_baseline_if_applicable or _default_complete_baseline
            ),
        ),
        offer_service=SimpleNamespace(),
        offer_logging_error=RuntimeError,
        channel_bonus_service=SimpleNamespace(),
        build_question_text=lambda **_kw: text,
    )
    return callback


def test_arena_baseline_fk_requires_same_duel_in_model_and_migration() -> None:
    duel_table = cast(Table, ArenaDuel.__table__)
    fk = next(
        constraint
        for constraint in duel_table.foreign_key_constraints
        if constraint.name == "fk_arena_duels_baseline_attempt_id_arena_attempts"
    )
    migration = Path("alembic/versions/f7a8b9c0d1e2_m47_open_arena_foundation.py").read_text()

    assert [column.name for column in fk.columns] == ["id", "baseline_attempt_id"]
    assert [f"{element.column.table.name}.{element.column.name}" for element in fk.elements] == [
        "arena_attempts.arena_duel_id",
        "arena_attempts.id",
    ]
    assert '"uq_arena_attempts_duel_id_id"' in migration
    assert '["id", "baseline_attempt_id"]' in migration
    assert '["arena_duel_id", "id"]' in migration


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

    async def _complete_baseline(*args, **kwargs):
        del args
        completed.append(kwargs)

    callback = await _continue_arena(
        _arena_result(arena_attempt_id, 7),
        _unexpected_start_session,
        complete_arena_creator_baseline_if_applicable=_complete_baseline,
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
async def test_continue_after_final_arena_challenger_round_does_not_publish_baseline() -> None:
    arena_attempt_id = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    completed: list[dict[str, object]] = []

    async def _unexpected_start_session(*_args, **_kwargs):
        pytest.fail("final ARENA_DUEL round must not start another session")

    async def _complete_if_applicable(*args, **kwargs):
        del args
        completed.append(kwargs)
        return None

    callback = await _continue_arena(
        _arena_result(arena_attempt_id, 7),
        _unexpected_start_session,
        complete_arena_creator_baseline_if_applicable=_complete_if_applicable,
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


def _return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner
