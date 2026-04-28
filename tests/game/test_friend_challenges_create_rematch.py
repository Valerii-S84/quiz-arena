from __future__ import annotations

from uuid import uuid4

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.service import friend_challenges_create
from tests.game.friend_challenges_unit_support import (
    FIXED_REMATCH_ID,
    NOW_UTC,
    SERIES_ID,
    Session,
    async_return,
    completed_challenge,
    duel,
)


@pytest.mark.asyncio
async def test_rematch_raises_when_challenge_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await friend_challenges_create.create_friend_challenge_rematch(
            Session(), initiator_user_id=11, challenge_id=uuid4(), now_utc=NOW_UTC
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_status", "initiator_user_id"),
    [(DUEL_STATUS_ACCEPTED, 11), ("COMPLETED", 999)],
    ids=["active_duel", "outsider"],
)
async def test_rematch_rejects_invalid_access(
    monkeypatch: pytest.MonkeyPatch,
    source_status: str,
    initiator_user_id: int,
) -> None:
    source = completed_challenge(status=source_status)
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(source),
    )
    monkeypatch.setattr(friend_challenges_create, "_expire_friend_challenge_if_due", _false)

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_create.create_friend_challenge_rematch(
            Session(),
            initiator_user_id=initiator_user_id,
            challenge_id=source.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_rematch_creates_direct_duel_and_emits_expired_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = completed_challenge()
    rematch = duel(id=FIXED_REMATCH_ID, creator_user_id=22, opponent_user_id=11)
    create_calls: list[dict[str, object]] = []
    expired_events: list[dict[str, object]] = []

    _patch_rematch_dependencies(monkeypatch, source, rematch, create_calls)
    monkeypatch.setattr(friend_challenges_create, "_expire_friend_challenge_if_due", _true)
    monkeypatch.setattr(
        friend_challenges_create,
        "_emit_friend_challenge_expired_event",
        _append_kwargs(expired_events),
    )

    result = await friend_challenges_create.create_friend_challenge_rematch(
        Session(), initiator_user_id=22, challenge_id=source.id, now_utc=NOW_UTC
    )

    assert result.challenge_id == FIXED_REMATCH_ID
    assert result.creator_user_id == 22
    assert result.opponent_user_id == 11
    assert create_calls[0]["series_id"] is None
    assert create_calls[0]["status"] == DUEL_STATUS_ACCEPTED
    assert expired_events[0]["challenge"] is source


@pytest.mark.asyncio
async def test_rematch_creates_next_series_game(monkeypatch: pytest.MonkeyPatch) -> None:
    source = completed_challenge(series_id=SERIES_ID, series_best_of=3)
    rematch = duel(id=FIXED_REMATCH_ID, series_id=SERIES_ID, series_game_number=2)
    create_calls: list[dict[str, object]] = []

    _patch_rematch_dependencies(monkeypatch, source, rematch, create_calls)
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "list_by_series_id_for_update",
        async_return([source]),
    )

    result = await friend_challenges_create.create_friend_challenge_rematch(
        Session(), initiator_user_id=22, challenge_id=source.id, now_utc=NOW_UTC
    )

    assert result.series_id == SERIES_ID
    assert result.series_game_number == 2
    assert create_calls[0]["series_best_of"] == 3


@pytest.mark.asyncio
async def test_rematch_resets_finished_series(monkeypatch: pytest.MonkeyPatch) -> None:
    source = completed_challenge(series_id=SERIES_ID, series_game_number=2, series_best_of=3)
    finished = completed_challenge(series_id=SERIES_ID, series_game_number=1, winner_user_id=11)
    rematch = duel(id=FIXED_REMATCH_ID)
    create_calls: list[dict[str, object]] = []

    _patch_rematch_dependencies(monkeypatch, source, rematch, create_calls)
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "list_by_series_id_for_update",
        async_return([finished, source]),
    )

    await friend_challenges_create.create_friend_challenge_rematch(
        Session(), initiator_user_id=22, challenge_id=source.id, now_utc=NOW_UTC
    )

    assert create_calls[0]["series_id"] is None
    assert create_calls[0]["series_game_number"] == 1
    assert create_calls[0]["series_best_of"] == 1


def _patch_rematch_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    source,
    rematch,
    create_calls: list[dict[str, object]],
) -> None:
    async def _fake_create_row(_session, **kwargs):
        create_calls.append(kwargs)
        rematch.question_ids = kwargs["question_ids"]
        return rematch

    monkeypatch.setattr(friend_challenges_create, "uuid4", lambda: FIXED_REMATCH_ID)
    monkeypatch.setattr(
        friend_challenges_create.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(source),
    )
    monkeypatch.setattr(friend_challenges_create, "_expire_friend_challenge_if_due", _false)
    monkeypatch.setattr(
        friend_challenges_create, "_resolve_friend_challenge_access_type", async_return("FREE")
    )
    monkeypatch.setattr(
        friend_challenges_create,
        "select_duel_question_ids",
        async_return(["rq-1", "rq-2", "rq-3", "rq-4", "rq-5"]),
    )
    monkeypatch.setattr(friend_challenges_create, "_create_friend_challenge_row", _fake_create_row)
    monkeypatch.setattr(
        friend_challenges_create, "emit_rematch_duel_created_events", async_return(None)
    )


def _false(**_kwargs) -> bool:
    return False


def _true(**_kwargs) -> bool:
    return True


def _append_kwargs(target: list[dict[str, object]]):
    async def _inner(*_args, **kwargs) -> None:
        target.append(kwargs)

    return _inner
