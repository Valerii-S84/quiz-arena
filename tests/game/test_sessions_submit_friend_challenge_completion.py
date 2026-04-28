from __future__ import annotations

import pytest

from app.game.friend_challenges.constants import DUEL_STATUS_COMPLETED
from app.game.sessions.service import sessions_submit_friend_challenge
from tests.game.friend_challenges_unit_support import (
    NOW_UTC,
    Session,
    async_return,
    challenge,
    quiz_session,
)


@pytest.mark.asyncio
async def test_expired_duel_event_and_tournament_progress_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(tournament_match_id="match-id")
    expired_events: list[dict[str, object]] = []
    progress_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )
    monkeypatch.setattr(sessions_submit_friend_challenge, "_expire_friend_challenge_if_due", _true)
    monkeypatch.setattr(
        sessions_submit_friend_challenge,
        "_emit_friend_challenge_expired_event",
        _append_kwargs(expired_events),
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge,
        "handle_tournament_duel_progress",
        _append_kwargs(progress_calls),
    )

    snapshot, round_completed, waiting = (
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=11, round_no=1),
            user_id=11,
            is_correct=False,
            now_utc=NOW_UTC,
        )
    )

    assert snapshot is not None
    assert round_completed is False
    assert waiting is True
    assert expired_events[0]["challenge"] is row
    assert progress_calls == [{"challenge": row, "user_id": 11, "now_utc": NOW_UTC}]


@pytest.mark.asyncio
async def test_creator_win_completes_duel_and_emits_analytics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(total_rounds=1, creator_score=1, creator_answered_round=1)
    analytics_events: list[dict[str, object]] = []

    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge,
        "emit_analytics_event",
        _append_kwargs(analytics_events),
    )

    snapshot, round_completed, waiting = (
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=22, round_no=1),
            user_id=22,
            is_correct=False,
            now_utc=NOW_UTC,
        )
    )

    assert snapshot is not None
    assert snapshot.status == DUEL_STATUS_COMPLETED
    assert snapshot.winner_user_id == 11
    assert round_completed is True
    assert waiting is False
    assert analytics_events[0]["event_type"] == "duel_completed"
    payload = analytics_events[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["winner_user_id"] == 11


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("is_correct", "expected_score", "expected_winner"),
    [(True, 1, 22), (False, 0, None)],
    ids=["opponent_wins", "draw"],
)
async def test_opponent_final_answer_resolves_winner(
    monkeypatch: pytest.MonkeyPatch,
    is_correct: bool,
    expected_score: int,
    expected_winner: int | None,
) -> None:
    row = challenge(total_rounds=1, creator_answered_round=1)
    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )
    monkeypatch.setattr(
        sessions_submit_friend_challenge, "emit_analytics_event", async_return(None)
    )

    snapshot, round_completed, waiting = (
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=22, round_no=1),
            user_id=22,
            is_correct=is_correct,
            now_utc=NOW_UTC,
        )
    )

    assert snapshot is not None
    assert snapshot.opponent_score == expected_score
    assert snapshot.winner_user_id == expected_winner
    assert round_completed is True
    assert waiting is False


@pytest.mark.asyncio
async def test_creator_done_status_is_set_before_opponent_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(total_rounds=5, creator_answered_round=4, opponent_answered_round=3)
    monkeypatch.setattr(
        sessions_submit_friend_challenge.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )

    snapshot, round_completed, waiting = (
        await sessions_submit_friend_challenge._apply_friend_challenge_answer(
            Session(),
            quiz_session=quiz_session(challenge_id=row.id, user_id=11, round_no=5),
            user_id=11,
            is_correct=True,
            now_utc=NOW_UTC,
        )
    )

    assert snapshot is not None
    assert snapshot.status == "CREATOR_DONE"
    assert snapshot.creator_finished_at == NOW_UTC
    assert round_completed is False
    assert waiting is True


def _true(**_kwargs) -> bool:
    return True


def _append_kwargs(target: list[dict[str, object]]):
    async def _inner(*_args, **kwargs) -> None:
        target.append(kwargs)

    return _inner
