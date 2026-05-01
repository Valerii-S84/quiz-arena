from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest

from app.db.models.arena_duels import ArenaAttempt
from app.db.repo.arena_duels_repo import ArenaDuelAcceptContext
from app.game.arena_duels import accept as accept_service
from app.game.arena_duels.constants import ARENA_ATTEMPT_ROLE_CHALLENGER, ARENA_SOURCE
from app.game.arena_duels.errors import ArenaDuelAccessError, ArenaDuelNotFoundError
from app.game.sessions.errors import DuelLimitRequiredError
from tests.game.arena_duels_accept_support import (
    MODE_CODE,
    NOW_UTC,
    active_duel,
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
        duel_limit_checked=True,
    )

    attempt = captured["attempt"]
    start_kwargs = cast(dict[str, object], captured["start_session"])
    assert isinstance(attempt, ArenaAttempt)
    assert attempt.arena_duel_id == duel.id
    assert attempt.user_id == 22
    assert attempt.role == ARENA_ATTEMPT_ROLE_CHALLENGER
    assert start_kwargs["source"] == ARENA_SOURCE
    assert start_kwargs["mode_code"] == MODE_CODE
    assert start_kwargs["arena_attempt_id"] == attempt.id
    assert start_kwargs["arena_round"] == 1
    assert start_kwargs["duel_limit_checked"] is True
    assert "forced_question_id" not in start_kwargs
    assert result.challenger_attempt_id == attempt.id
    assert result.duel.question_ids == tuple(question_ids())


@pytest.mark.asyncio
async def test_accept_arena_duel_requires_limit_before_locked_read(
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
            duel_limit_checked=False,
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
            duel_limit_checked=True,
        )


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
            duel_limit_checked=True,
        )
