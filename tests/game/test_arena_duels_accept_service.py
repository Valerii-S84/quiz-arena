from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest

from app.db.models.arena_duels import ArenaAttempt
from app.db.repo.arena_duels_repo import ArenaDuelAcceptContext
from app.game.arena_duels import accept as accept_service
from app.game.arena_duels.constants import ARENA_ATTEMPT_ROLE_CHALLENGER, ARENA_SOURCE
from app.game.arena_duels.errors import ArenaDuelAccessError, ArenaDuelNotFoundError
from app.game.duels.limits import DUEL_ACCESS_FREE
from app.game.sessions.errors import DuelLimitRequiredError
from tests.game.arena_duels_accept_support import (
    MODE_CODE,
    NOW_UTC,
    active_duel,
    baseline_attempt,
    challenger_attempt,
    question_ids,
    start_result,
)
from tests.type_helpers import AsyncSessionStub


@pytest.mark.asyncio
async def test_accept_arena_duel_creates_attempt_and_starts_first_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duel = active_duel()
    captured: dict[str, object] = {}

    async def _get_context(*_args, **_kwargs):
        return ArenaDuelAcceptContext(duel=duel, existing_attempt=None)

    async def _create_attempt(*_args, **kwargs):
        captured["attempt"] = kwargs["attempt"]
        return kwargs["attempt"]

    async def _start_session(*_args, **kwargs):
        captured["start_session"] = kwargs
        return start_result()

    monkeypatch.setattr(
        accept_service.ArenaDuelsRepo, "get_accept_context_for_update", _get_context
    )
    monkeypatch.setattr(accept_service.ArenaDuelsRepo, "create_attempt", _create_attempt)
    monkeypatch.setattr(accept_service, "start_session", _start_session)

    result = await accept_service.accept_arena_duel(
        AsyncSessionStub(),
        duel_id=duel.id,
        user_id=22,
        now_utc=NOW_UTC,
        access_type=DUEL_ACCESS_FREE,
    )

    attempt = captured["attempt"]
    start_kwargs = cast(dict[str, object], captured["start_session"])
    assert isinstance(attempt, ArenaAttempt)
    assert attempt.arena_duel_id == duel.id
    assert attempt.user_id == 22
    assert attempt.role == ARENA_ATTEMPT_ROLE_CHALLENGER
    assert attempt.access_type == DUEL_ACCESS_FREE
    assert start_kwargs["source"] == ARENA_SOURCE
    assert start_kwargs["mode_code"] == MODE_CODE
    assert start_kwargs["arena_attempt_id"] == attempt.id
    assert start_kwargs["arena_round"] == 1
    assert start_kwargs["duel_limit_checked"] is True
    assert "forced_question_id" not in start_kwargs
    assert result.challenger_attempt_id == attempt.id
    assert result.duel.question_ids == tuple(question_ids())


@pytest.mark.asyncio
async def test_accept_arena_duel_requires_resolved_access_before_locked_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unexpected_get_context(*_args, **_kwargs):
        pytest.fail("Arena accept must not read rows before the duel-limit gate")

    monkeypatch.setattr(
        accept_service.ArenaDuelsRepo,
        "get_accept_context_for_update",
        _unexpected_get_context,
    )

    with pytest.raises(DuelLimitRequiredError):
        await accept_service.accept_arena_duel(
            AsyncSessionStub(),
            duel_id=uuid4(),
            user_id=22,
            now_utc=NOW_UTC,
            access_type="",
        )


@pytest.mark.asyncio
async def test_accept_arena_duel_rejects_missing_duel(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _get_context(*_args, **_kwargs):
        return None

    async def _unexpected_create_attempt(*_args, **_kwargs):
        pytest.fail("missing Arena-Duell must not create an attempt")

    monkeypatch.setattr(
        accept_service.ArenaDuelsRepo, "get_accept_context_for_update", _get_context
    )
    monkeypatch.setattr(accept_service.ArenaDuelsRepo, "create_attempt", _unexpected_create_attempt)

    with pytest.raises(ArenaDuelNotFoundError):
        await accept_service.accept_arena_duel(
            AsyncSessionStub(),
            duel_id=uuid4(),
            user_id=22,
            now_utc=NOW_UTC,
            access_type=DUEL_ACCESS_FREE,
        )


@pytest.mark.asyncio
async def test_get_arena_duel_accept_preview_returns_current_best_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duel = active_duel()
    baseline = baseline_attempt(duel_id=duel.id, attempt_id=duel.baseline_attempt_id)
    baseline.score = 6
    baseline.time_ms = 48_000
    current_best = challenger_attempt(duel_id=duel.id, user_id=33)
    current_best.score = 7
    current_best.time_ms = 52_000
    current_best.completed_at = NOW_UTC

    async def _get_context(*_args, **_kwargs):
        return ArenaDuelAcceptContext(duel=duel, existing_attempt=None)

    async def _list_completed_attempts(*_args, **_kwargs):
        return [current_best, baseline]

    monkeypatch.setattr(
        accept_service.ArenaDuelsRepo, "get_accept_context_for_update", _get_context
    )
    monkeypatch.setattr(
        accept_service.ArenaDuelsRepo,
        "list_completed_attempts_for_duel",
        _list_completed_attempts,
    )

    result = await accept_service.get_arena_duel_accept_preview(
        AsyncSessionStub(),
        duel_id=duel.id,
        user_id=22,
        now_utc=NOW_UTC,
    )

    assert result.duel_id == duel.id
    assert result.creator_user_id == 33
    assert result.baseline_attempt_id == current_best.id
    assert result.score == 7
    assert result.time_ms == 52_000


@pytest.mark.asyncio
async def test_accept_arena_duel_rejects_active_duel_without_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duel = active_duel()
    duel.baseline_attempt_id = None

    await _assert_access_rejected_before_attempt_create(monkeypatch, duel=duel)


@pytest.mark.asyncio
@pytest.mark.parametrize("question_ids_payload", [["one"], ["arena-q"] * 6 + [None]])
async def test_accept_arena_duel_rejects_invalid_question_set(
    monkeypatch: pytest.MonkeyPatch,
    question_ids_payload: list[object],
) -> None:
    duel = active_duel()
    duel.question_ids = question_ids_payload  # type: ignore[assignment]

    await _assert_access_rejected_before_attempt_create(monkeypatch, duel=duel)


async def _assert_access_rejected_before_attempt_create(
    monkeypatch: pytest.MonkeyPatch,
    *,
    duel,
) -> None:
    async def _get_context(*_args, **_kwargs):
        return ArenaDuelAcceptContext(duel=duel, existing_attempt=None)

    async def _unexpected_create_attempt(*_args, **_kwargs):
        pytest.fail("invalid Arena-Duell must not create an attempt")

    monkeypatch.setattr(
        accept_service.ArenaDuelsRepo, "get_accept_context_for_update", _get_context
    )
    monkeypatch.setattr(accept_service.ArenaDuelsRepo, "create_attempt", _unexpected_create_attempt)

    with pytest.raises(ArenaDuelAccessError):
        await accept_service.accept_arena_duel(
            AsyncSessionStub(),
            duel_id=duel.id,
            user_id=22,
            now_utc=NOW_UTC,
            access_type=DUEL_ACCESS_FREE,
        )
