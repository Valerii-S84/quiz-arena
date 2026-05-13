from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.game.sessions.service import friend_challenges_rounds, friend_challenges_rounds_start
from app.game.tournaments.constants import TOURNAMENT_TYPE_DAILY_ARENA
from tests.game.friend_challenges_unit_support import (
    NOW_UTC,
    TOURNAMENT_ID,
    TOURNAMENT_MATCH_ID,
    Session,
    async_return,
    challenge,
    start_result,
)


@pytest.mark.asyncio
async def test_round_start_returns_already_answered_when_user_finished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(status="CREATOR_DONE", creator_answered_round=5, opponent_answered_round=3)
    monkeypatch.setattr(
        friend_challenges_rounds.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )
    monkeypatch.setattr(friend_challenges_rounds_start, "start_session", _unexpected_start_session)

    result = await friend_challenges_rounds.start_friend_challenge_round(
        Session(),
        user_id=11,
        challenge_id=row.id,
        idempotency_key="round:done",
        now_utc=NOW_UTC,
    )

    assert result.start_result is None
    assert result.snapshot.challenge_id == row.id
    assert result.waiting_for_opponent is True
    assert result.already_answered_current_round is True


@pytest.mark.asyncio
async def test_round_start_replays_existing_session_with_daily_arena_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = challenge(tournament_match_id=TOURNAMENT_MATCH_ID)
    existing = SimpleNamespace(id=uuid4(), question_id="existing-q")
    replay = start_result(question_id="existing-q", idempotent_replay=True)

    monkeypatch.setattr(
        friend_challenges_rounds.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )
    monkeypatch.setattr(
        friend_challenges_rounds_start.QuizSessionsRepo,
        "get_by_friend_challenge_round_user",
        async_return(existing),
    )
    monkeypatch.setattr(
        friend_challenges_rounds_start,
        "_build_start_result_from_existing_session",
        async_return(replay),
    )
    monkeypatch.setattr(
        friend_challenges_rounds.TournamentMatchesRepo,
        "get_by_id_for_update",
        async_return(SimpleNamespace(tournament_id=TOURNAMENT_ID)),
    )
    monkeypatch.setattr(
        friend_challenges_rounds.TournamentsRepo,
        "get_by_id",
        async_return(SimpleNamespace(type=TOURNAMENT_TYPE_DAILY_ARENA)),
    )

    result = await friend_challenges_rounds.start_friend_challenge_round(
        Session(),
        user_id=11,
        challenge_id=row.id,
        idempotency_key="round:replay",
        now_utc=NOW_UTC,
    )

    assert result.start_result is replay
    assert replay.session.header_mode_label_override == "Daily Arena Cup"
    assert result.waiting_for_opponent is False


@pytest.mark.asyncio
async def test_round_start_reuses_shared_round_question(monkeypatch: pytest.MonkeyPatch) -> None:
    row = challenge(question_ids=["planned-q"])
    start_calls: list[dict[str, object]] = []

    await _run_start_with_question_sources(
        monkeypatch,
        row=row,
        shared_round_session=SimpleNamespace(question_id="shared-q"),
        start_calls=start_calls,
    )

    assert start_calls[0]["forced_question_id"] == "shared-q"
    assert start_calls[0]["friend_challenge_round"] == 1


async def _run_start_with_question_sources(
    monkeypatch: pytest.MonkeyPatch,
    *,
    row,
    shared_round_session,
    start_calls: list[dict[str, object]],
):
    async def _fake_start_session(_session, **kwargs):
        start_calls.append(kwargs)
        return start_result(question_id=str(kwargs["forced_question_id"]))

    monkeypatch.setattr(
        friend_challenges_rounds.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(row),
    )
    monkeypatch.setattr(
        friend_challenges_rounds_start.QuizSessionsRepo,
        "get_by_friend_challenge_round_user",
        async_return(None),
    )
    monkeypatch.setattr(
        friend_challenges_rounds_start.QuizSessionsRepo,
        "get_by_friend_challenge_round_any_user",
        async_return(shared_round_session),
    )
    monkeypatch.setattr(friend_challenges_rounds_start, "start_session", _fake_start_session)

    return await friend_challenges_rounds.start_friend_challenge_round(
        Session(),
        user_id=22,
        challenge_id=row.id,
        idempotency_key="round:start",
        now_utc=NOW_UTC,
    )


async def _unexpected_start_session(*_args, **_kwargs):
    pytest.fail("no new round session should be started")
