from __future__ import annotations

import pytest

from app.game.friend_challenges.constants import (
    DUEL_STATUS_ACCEPTED,
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_OPPONENT_DONE,
)
from app.game.sessions.service import sessions_submit_friend_challenge
from tests.game.friend_challenges_unit_support import (
    NOW_UTC,
    Session,
    async_return,
    challenge,
    quiz_session,
)


@pytest.mark.asyncio
async def test_opponent_correct_answer_scores_and_waits_for_creator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge()
    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )

    snapshot, round_completed, waiting = (
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=22, round_no=1),
            user_id=22,
            is_correct=True,
            now_utc=NOW_UTC,
        )
    )

    assert snapshot is not None
    assert snapshot.status == DUEL_STATUS_ACCEPTED
    assert snapshot.opponent_score == 1
    assert snapshot.current_round == 2
    assert round_completed is False
    assert waiting is True


@pytest.mark.asyncio
async def test_creator_done_status_is_set_before_opponent_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(total_rounds=7, creator_answered_round=6, opponent_answered_round=3)
    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )

    snapshot, round_completed, waiting = (
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=11, round_no=7),
            user_id=11,
            is_correct=True,
            now_utc=NOW_UTC,
        )
    )

    assert snapshot is not None
    assert snapshot.status == DUEL_STATUS_CREATOR_DONE
    assert snapshot.creator_finished_at == NOW_UTC
    assert round_completed is False
    assert waiting is True


@pytest.mark.asyncio
async def test_opponent_done_status_is_set_before_creator_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(total_rounds=7, creator_answered_round=3, opponent_answered_round=6)
    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )

    snapshot, round_completed, waiting = (
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=22, round_no=7),
            user_id=22,
            is_correct=True,
            now_utc=NOW_UTC,
        )
    )

    assert snapshot is not None
    assert snapshot.status == DUEL_STATUS_OPPONENT_DONE
    assert snapshot.opponent_finished_at == NOW_UTC
    assert round_completed is False
    assert waiting is True
