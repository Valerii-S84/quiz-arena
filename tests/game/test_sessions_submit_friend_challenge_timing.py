from __future__ import annotations

import pytest

from app.game.sessions.service import (
    sessions_submit_friend_challenge,
    sessions_submit_friend_challenge_resolution,
)
from tests.game.friend_challenges_unit_support import (
    NOW_UTC,
    Session,
    async_return,
    challenge,
    quiz_session,
)


@pytest.mark.asyncio
async def test_canonical_friend_duel_uses_time_tie_break_for_equal_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(
        total_rounds=7,
        creator_score=5,
        opponent_score=5,
        creator_answered_round=7,
        opponent_answered_round=6,
        question_ids=[f"q-{index}" for index in range(1, 8)],
    )

    async def _sum_time(*_args, **kwargs):
        return {11: 61_000, 22: 52_000}[kwargs["user_id"]]

    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge_resolution.QuizSessionsRepo,
        "sum_completed_duration_ms_for_friend_challenge_user",
        _sum_time,
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge, "emit_analytics_event", async_return(None)
    )

    snapshot, round_completed, waiting = (
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=22, round_no=7),
            user_id=22,
            is_correct=False,
            now_utc=NOW_UTC,
        )
    )

    assert snapshot is not None
    assert snapshot.winner_user_id == 22
    assert round_completed is True
    assert waiting is False


@pytest.mark.asyncio
async def test_tournament_friend_duel_keeps_score_only_draw_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(
        total_rounds=7,
        creator_score=5,
        opponent_score=5,
        creator_answered_round=7,
        opponent_answered_round=6,
        question_ids=[f"q-{index}" for index in range(1, 8)],
        tournament_match_id="match-id",
    )

    async def _unexpected_sum_time(*_args, **_kwargs):
        pytest.fail("private tournament friend-duels must not use time tie-break")

    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge_resolution.QuizSessionsRepo,
        "sum_completed_duration_ms_for_friend_challenge_user",
        _unexpected_sum_time,
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge, "emit_analytics_event", async_return(None)
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge,
        "handle_tournament_duel_progress",
        async_return(None),
    )

    snapshot, round_completed, waiting = (
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=22, round_no=7),
            user_id=22,
            is_correct=False,
            now_utc=NOW_UTC,
        )
    )

    assert snapshot is not None
    assert snapshot.winner_user_id is None
    assert round_completed is True
    assert waiting is False
