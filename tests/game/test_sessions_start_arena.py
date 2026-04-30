from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.db.models.quiz_sessions import QuizSession
from app.game.sessions.errors import DuelLimitRequiredError
from app.game.sessions.service import sessions_start
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 4, 30, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_arena_duel_start_requires_duel_limit_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _unexpected_energy_consume(*_args, **_kwargs):
        pytest.fail("ARENA_DUEL must fail on missing duel gate before energy")

    monkeypatch.setattr(sessions_start.EnergyService, "consume_quiz", _unexpected_energy_consume)

    with pytest.raises(DuelLimitRequiredError):
        await sessions_start.start_session(
            _Session(),
            user_id=11,
            mode_code="QUICK_MIX_A1A2",
            source="ARENA_DUEL",
            idempotency_key="arena:missing-gate",
            now_utc=NOW_UTC,
            arena_attempt_id=uuid4(),
            arena_round=1,
            forced_question_id="arena-q-1",
        )


@pytest.mark.asyncio
async def test_arena_duel_start_is_zero_energy_after_duel_limit_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_sessions: list[QuizSession] = []
    arena_attempt_id = uuid4()

    async def _fake_get_existing(*_args, **_kwargs):
        return None

    async def _unexpected_energy_consume(*_args, **_kwargs):
        pytest.fail("ARENA_DUEL sessions must not consume quiz energy")

    async def _fake_get_question_by_id(*_args, **_kwargs):
        return SimpleNamespace(
            question_id="arena-q-3",
            text="Question?",
            options=("A", "B", "C", "D"),
            category="Arena",
        )

    async def _fake_create(*_args, **kwargs):
        created_sessions.append(kwargs["quiz_session"])
        return kwargs["quiz_session"]

    monkeypatch.setattr(
        sessions_start.QuizSessionsRepo,
        "get_by_idempotency_key",
        _fake_get_existing,
    )
    monkeypatch.setattr(sessions_start.EnergyService, "consume_quiz", _unexpected_energy_consume)
    monkeypatch.setattr(sessions_start.QuizSessionsRepo, "create", _fake_create)

    from app.game.sessions import service as service_module

    monkeypatch.setattr(service_module, "get_question_by_id", _fake_get_question_by_id)

    result = await sessions_start.start_session(
        _Session(),
        user_id=11,
        mode_code="QUICK_MIX_A1A2",
        source="ARENA_DUEL",
        idempotency_key="arena:checked",
        now_utc=NOW_UTC,
        arena_attempt_id=arena_attempt_id,
        arena_round=3,
        forced_question_id="arena-q-3",
        duel_limit_checked=True,
    )

    created = created_sessions[0]
    assert created.source == "ARENA_DUEL"
    assert created.energy_cost_total == 0
    assert created.arena_attempt_id == arena_attempt_id
    assert created.arena_round == 3
    assert result.energy_free == 0
    assert result.energy_paid == 0
    assert result.session.question_number == 3
    assert result.session.total_questions == 7
