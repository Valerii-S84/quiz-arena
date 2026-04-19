from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.service import friend_challenges_series_start
from tests.type_helpers import AsyncSessionStub

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _challenge(
    *,
    status: str = "COMPLETED",
    creator_user_id: int = 101,
    opponent_user_id: int | None = 202,
    series_id: UUID | None = None,
    series_game_number: int = 1,
    series_best_of: int = 1,
    winner_user_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        mode_code="QUICK_MIX_A1A2",
        total_rounds=7,
        status=status,
        series_id=series_id,
        series_game_number=series_game_number,
        series_best_of=series_best_of,
        winner_user_id=winner_user_id,
        expires_at=NOW_UTC + timedelta(minutes=15),
    )


def _duel(
    *,
    duel_id: UUID | None = None,
    access_type: str = "FREE",
    series_id: UUID | None = None,
    series_game_number: int = 1,
    series_best_of: int = 3,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=duel_id or uuid4(),
        mode_code="QUICK_MIX_A1A2",
        access_type=access_type,
        total_rounds=7,
        series_id=series_id,
        series_game_number=series_game_number,
        series_best_of=series_best_of,
        expires_at=NOW_UTC + timedelta(minutes=15),
    )


def _draft(
    *,
    creator_user_id: int,
    opponent_user_id: int | None,
    access_type: str,
    series_id: UUID,
    series_game_number: int,
    series_best_of: int,
) -> SimpleNamespace:
    return SimpleNamespace(
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        access_type=access_type,
        total_rounds=7,
        series_id=series_id,
        series_game_number=series_game_number,
        series_best_of=series_best_of,
        status=DUEL_STATUS_ACCEPTED,
    )


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


def _context(*, challenge: SimpleNamespace, opponent_user_id: int) -> SimpleNamespace:
    return SimpleNamespace(
        challenge=challenge,
        opponent_user_id=opponent_user_id,
    )


@pytest.mark.asyncio
async def test_create_friend_challenge_best_of_three_raises_when_challenge_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _raise_not_found(*args, **kwargs):
        del args, kwargs
        raise FriendChallengeNotFoundError

    monkeypatch.setattr(
        friend_challenges_series_start,
        "load_friend_challenge_series_context",
        _raise_not_found,
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_series_start.create_friend_challenge_best_of_three(
            _Session(), initiator_user_id=101, challenge_id=uuid4(), now_utc=NOW_UTC
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "initiator_user_id"),
    [("ACCEPTED", 101), ("COMPLETED", 999)],
    ids=["active_status_rejected", "outsider_rejected"],
)
async def test_create_friend_challenge_best_of_three_rejects_invalid_access(
    monkeypatch: pytest.MonkeyPatch, status: str, initiator_user_id: int
) -> None:
    challenge = _challenge(status=status)

    async def _raise_access_error(*args, **kwargs):
        del args, kwargs
        raise FriendChallengeAccessError

    monkeypatch.setattr(
        friend_challenges_series_start,
        "load_friend_challenge_series_context",
        _raise_access_error,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_series_start.create_friend_challenge_best_of_three(
            _Session(),
            initiator_user_id=initiator_user_id,
            challenge_id=challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_create_friend_challenge_best_of_three_creates_series_duel_and_emits_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    fixed_series_id = uuid4()
    draft = _draft(
        creator_user_id=101,
        opponent_user_id=202,
        access_type="FREE",
        series_id=fixed_series_id,
        series_game_number=1,
        series_best_of=5,
    )
    duel = _duel(series_id=fixed_series_id, series_best_of=5)
    create_calls: list[dict[str, object]] = []
    series_event_calls: list[dict[str, Any]] = []

    async def _fake_create_row(session, **kwargs):
        del session
        create_calls.append(kwargs)
        return duel

    async def _fake_emit_series_started(session, **kwargs):
        del session
        series_event_calls.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_series_start,
        "load_friend_challenge_series_context",
        _async_return(_context(challenge=challenge, opponent_user_id=202)),
    )
    monkeypatch.setattr(
        friend_challenges_series_start,
        "build_series_start_friend_challenge_draft",
        _async_return(draft),
    )
    monkeypatch.setattr(
        friend_challenges_series_start,
        "create_series_friend_challenge_from_draft",
        _fake_create_row,
    )
    monkeypatch.setattr(
        friend_challenges_series_start,
        "emit_series_started_duel_created_events",
        _fake_emit_series_started,
    )
    monkeypatch.setattr(
        friend_challenges_series_start,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: {"challenge_id": challenge_row.id},
    )

    result = await friend_challenges_series_start.create_friend_challenge_best_of_three(
        _Session(),
        initiator_user_id=101,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
        best_of=5,
    )

    assert result == {"challenge_id": duel.id}
    assert create_calls == [
        {
            "draft": draft,
            "now_utc": NOW_UTC,
        }
    ]
    assert series_event_calls == [
        {
            "duel": duel,
            "source_challenge_id": challenge.id,
            "opponent_user_id": 202,
            "happened_at": NOW_UTC,
            "source": friend_challenges_series_start.EVENT_SOURCE_BOT,
            "initiator_user_id": 101,
        }
    ]
