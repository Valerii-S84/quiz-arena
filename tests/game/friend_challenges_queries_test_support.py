from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, TypeVar
from uuid import UUID, uuid4

from tests.type_helpers import AsyncSessionStub

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)

T = TypeVar("T")


class FriendChallengeQueriesSession(AsyncSessionStub):
    pass


def build_challenge(
    *,
    status: str = "ACCEPTED",
    creator_user_id: int = 11,
    opponent_user_id: int | None = 22,
    series_id: UUID | None = None,
    series_game_number: int = 1,
    series_best_of: int = 1,
    winner_user_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        status=status,
        series_id=series_id,
        series_game_number=series_game_number,
        series_best_of=series_best_of,
        winner_user_id=winner_user_id,
        expires_at=NOW_UTC,
    )


def async_return(value: T) -> Callable[..., Awaitable[T]]:
    async def _inner(*_args: Any, **_kwargs: Any) -> T:
        return value

    return _inner
