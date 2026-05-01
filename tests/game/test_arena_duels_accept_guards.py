from __future__ import annotations

from datetime import timedelta

import pytest

from app.db.repo.arena_duels_repo import ArenaDuelAcceptContext
from app.game.arena_duels import accept as accept_service
from app.game.arena_duels.constants import ARENA_DUEL_STATUS_ACTIVE, ARENA_DUEL_STATUS_DRAFT
from app.game.arena_duels.errors import (
    ArenaDuelAccessError,
    ArenaDuelAlreadyAttemptedError,
    ArenaDuelExpiredError,
    ArenaDuelOwnAttemptError,
)
from app.game.duels.limits import DUEL_ACCESS_FREE
from tests.game.arena_duels_accept_support import NOW_UTC, active_duel, challenger_attempt
from tests.type_helpers import AsyncSessionStub


@pytest.mark.asyncio
async def test_accept_arena_duel_rejects_creator_self_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duel = active_duel(creator_user_id=11)

    await _assert_accept_rejected(
        monkeypatch,
        context=ArenaDuelAcceptContext(duel=duel, existing_attempt=None),
        expected_error=ArenaDuelOwnAttemptError,
        user_id=11,
    )


@pytest.mark.asyncio
async def test_accept_arena_duel_rejects_duplicate_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duel = active_duel()
    existing_attempt = challenger_attempt(duel_id=duel.id)

    await _assert_accept_rejected(
        monkeypatch,
        context=ArenaDuelAcceptContext(duel=duel, existing_attempt=existing_attempt),
        expected_error=ArenaDuelAlreadyAttemptedError,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expires_offset", "expected_error"),
    [
        (ARENA_DUEL_STATUS_DRAFT, timedelta(hours=1), ArenaDuelAccessError),
        (ARENA_DUEL_STATUS_ACTIVE, timedelta(), ArenaDuelExpiredError),
    ],
)
async def test_accept_arena_duel_rejects_inactive_or_expired_duel(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    expires_offset: timedelta,
    expected_error: type[ArenaDuelAccessError],
) -> None:
    duel = active_duel()
    duel.status = status
    duel.expires_at = NOW_UTC + expires_offset

    await _assert_accept_rejected(
        monkeypatch,
        context=ArenaDuelAcceptContext(duel=duel, existing_attempt=None),
        expected_error=expected_error,
    )


async def _assert_accept_rejected(
    monkeypatch: pytest.MonkeyPatch,
    *,
    context: ArenaDuelAcceptContext,
    expected_error: type[ArenaDuelAccessError],
    user_id: int = 22,
) -> None:
    async def _get_context(*_args, **_kwargs):
        return context

    async def _unexpected_create_attempt(*_args, **_kwargs):
        pytest.fail("rejected Arena-Duell must not create an attempt")

    monkeypatch.setattr(
        accept_service.ArenaDuelsRepo, "get_accept_context_for_update", _get_context
    )
    monkeypatch.setattr(accept_service.ArenaDuelsRepo, "create_attempt", _unexpected_create_attempt)

    with pytest.raises(expected_error):
        await accept_service.accept_arena_duel(
            AsyncSessionStub(),
            duel_id=context.duel.id,
            user_id=user_id,
            now_utc=NOW_UTC,
            access_type=DUEL_ACCESS_FREE,
        )
