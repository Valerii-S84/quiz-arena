from __future__ import annotations

from uuid import uuid4

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_ACCEPTED
from app.game.sessions.errors import FriendChallengeAccessError, FriendChallengeNotFoundError
from app.game.sessions.service import sessions_submit_friend_challenge
from tests.game.friend_challenges_unit_support import (
    NOW_UTC,
    Session,
    async_return,
    challenge,
    non_friend_quiz_session,
    quiz_session,
)


@pytest.mark.asyncio
async def test_non_friend_session_does_not_query_challenge(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _unexpected_lookup(*_args, **_kwargs):
        pytest.fail("non-friend sessions should not query friend challenge state")

    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        _unexpected_lookup,
    )

    result = await sessions_submit_friend_challenge._apply_friend_challenge_answer(
        Session(),
        quiz_session=non_friend_quiz_session(),
        user_id=11,
        is_correct=True,
        now_utc=NOW_UTC,
    )

    assert result == (None, False, False)


@pytest.mark.asyncio
async def test_missing_challenge_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(None),
    )

    with pytest.raises(FriendChallengeNotFoundError):
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=uuid4(), user_id=11, round_no=1),
            user_id=11,
            is_correct=True,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_creator_correct_answer_waits_for_opponent(monkeypatch: pytest.MonkeyPatch) -> None:
    row = challenge()
    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )

    snapshot, round_completed, waiting = (
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=11, round_no=1),
            user_id=11,
            is_correct=True,
            now_utc=NOW_UTC,
        )
    )

    assert snapshot is not None
    assert snapshot.status == DUEL_STATUS_ACCEPTED
    assert snapshot.creator_score == 1
    assert snapshot.current_round == 2
    assert round_completed is False
    assert waiting is True


@pytest.mark.asyncio
async def test_creator_replay_does_not_rescore(monkeypatch: pytest.MonkeyPatch) -> None:
    row = challenge(creator_score=1, creator_answered_round=1)
    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )

    snapshot, round_completed, waiting = (
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=11, round_no=1),
            user_id=11,
            is_correct=True,
            now_utc=NOW_UTC,
        )
    )

    assert snapshot is not None
    assert snapshot.creator_score == 1
    assert row.creator_answered_round == 1
    assert round_completed is False
    assert waiting is True


@pytest.mark.asyncio
async def test_opponent_incorrect_answer_completes_round(monkeypatch: pytest.MonkeyPatch) -> None:
    row = challenge(creator_score=2, opponent_score=1, creator_answered_round=2)
    row.opponent_answered_round = 1
    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )

    snapshot, round_completed, waiting = (
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=22, round_no=2),
            user_id=22,
            is_correct=False,
            now_utc=NOW_UTC,
        )
    )

    assert snapshot is not None
    assert snapshot.creator_score == 2
    assert snapshot.opponent_score == 1
    assert snapshot.current_round == 3
    assert round_completed is True
    assert waiting is False


@pytest.mark.asyncio
async def test_non_participant_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    row = challenge()
    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )

    with pytest.raises(FriendChallengeAccessError):
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=999, round_no=1),
            user_id=999,
            is_correct=True,
            now_utc=NOW_UTC,
        )
