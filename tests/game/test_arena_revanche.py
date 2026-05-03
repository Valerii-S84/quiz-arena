from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import ArenaAttemptDuelContext
from app.game.arena_duels import revanche
from app.game.arena_duels.errors import ArenaDuelAccessError
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
DUEL_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SOURCE_ATTEMPT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _arena_context(*, receiver_user_id: int = 22) -> ArenaAttemptDuelContext:
    return ArenaAttemptDuelContext(
        attempt=cast(
            ArenaAttempt,
            SimpleNamespace(
                id=SOURCE_ATTEMPT_ID,
                user_id=receiver_user_id,
                completed_at=NOW_UTC,
                score=7,
                time_ms=52_000,
            ),
        ),
        duel=cast(
            ArenaDuel,
            SimpleNamespace(
                id=DUEL_ID,
                mode_code="QUICK_MIX_A1A2",
            ),
        ),
    )


@pytest.mark.asyncio
async def test_arena_revanche_allowed_after_arena_duel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        revanche.ArenaDuelsRepo,
        "get_attempt_duel_for_update",
        _async_return(_arena_context()),
    )
    monkeypatch.setattr(
        revanche.ArenaDuelsRepo,
        "has_completed_attempt_for_user",
        _async_return(True),
    )

    context = await revanche.load_arena_revanche_context(
        AsyncSessionStub(),
        sender_user_id=11,
        source_attempt_id=SOURCE_ATTEMPT_ID,
    )

    assert context.sender_user_id == 11
    assert context.receiver_user_id == 22
    assert context.source_attempt_id == SOURCE_ATTEMPT_ID


@pytest.mark.asyncio
async def test_arena_revanche_denied_without_prior_interaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        revanche.ArenaDuelsRepo,
        "get_attempt_duel_for_update",
        _async_return(_arena_context()),
    )
    monkeypatch.setattr(
        revanche.ArenaDuelsRepo,
        "has_completed_attempt_for_user",
        _async_return(False),
    )

    with pytest.raises(ArenaDuelAccessError):
        await revanche.load_arena_revanche_context(
            AsyncSessionStub(),
            sender_user_id=11,
            source_attempt_id=SOURCE_ATTEMPT_ID,
        )


@pytest.mark.asyncio
async def test_arena_revanche_denied_for_unrelated_random_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        revanche.ArenaDuelsRepo,
        "get_attempt_duel_for_update",
        _async_return(_arena_context(receiver_user_id=11)),
    )
    monkeypatch.setattr(
        revanche.ArenaDuelsRepo,
        "has_completed_attempt_for_user",
        _async_return(True),
    )

    with pytest.raises(ArenaDuelAccessError):
        await revanche.load_arena_revanche_context(
            AsyncSessionStub(),
            sender_user_id=11,
            source_attempt_id=SOURCE_ATTEMPT_ID,
        )


@pytest.mark.asyncio
async def test_premium_does_not_bypass_revanche_interaction_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolved_access: list[object] = []
    monkeypatch.setattr(
        revanche.ArenaDuelsRepo,
        "get_attempt_duel_for_update",
        _async_return(_arena_context()),
    )
    monkeypatch.setattr(
        revanche.ArenaDuelsRepo,
        "has_completed_attempt_for_user",
        _async_return(False),
    )
    monkeypatch.setattr(
        revanche.DuelLimitService,
        "resolve_revanche_access_type",
        _append_and_return(resolved_access, "PREMIUM"),
    )

    with pytest.raises(ArenaDuelAccessError):
        await revanche.prepare_arena_revanche_request(
            AsyncSessionStub(),
            sender_user_id=11,
            source_attempt_id=SOURCE_ATTEMPT_ID,
            now_utc=NOW_UTC,
        )

    assert resolved_access == []


def _async_return(value):
    async def _inner(*_args, **_kwargs):
        return value

    return _inner


def _append_and_return(target: list[object], value: object):
    async def _inner(*_args, **_kwargs):
        target.append(value)
        return value

    return _inner


def _fail(message: str):
    async def _inner(*_args, **_kwargs):
        pytest.fail(message)

    return _inner
