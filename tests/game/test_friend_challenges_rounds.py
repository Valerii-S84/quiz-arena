from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.service import friend_challenges_rounds, friend_challenges_rounds_state
from app.game.sessions.types import (
    FriendChallengeRoundStartResult,
    FriendChallengeSnapshot,
    SessionQuestionView,
    StartSessionResult,
)
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
TOURNAMENT_MATCH_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class _Session(AsyncSessionStub):
    pass


def _async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


def _challenge(**overrides: object) -> FriendChallenge:
    payload: dict[str, object] = {
        "mode_code": "QUICK_MIX_A1A2",
        "total_rounds": 7,
        "tournament_match_id": TOURNAMENT_MATCH_ID,
    }
    payload.update(overrides)
    return build_friend_challenge(**payload)


def _snapshot(challenge: FriendChallenge) -> FriendChallengeSnapshot:
    return FriendChallengeSnapshot(
        challenge_id=challenge.id,
        invite_token=challenge.invite_token,
        challenge_type=challenge.challenge_type,
        mode_code=challenge.mode_code,
        access_type=challenge.access_type,
        status=challenge.status,
        creator_user_id=challenge.creator_user_id,
        opponent_user_id=challenge.opponent_user_id,
        current_round=challenge.current_round,
        total_rounds=challenge.total_rounds,
        creator_score=challenge.creator_score,
        opponent_score=challenge.opponent_score,
        tournament_match_id=challenge.tournament_match_id,
    )


def _start_result(
    *, session_id: UUID | None = None, question_id: str = "q-1"
) -> StartSessionResult:
    return StartSessionResult(
        session=SessionQuestionView(
            session_id=session_id or uuid4(),
            question_id=question_id,
            text="Question",
            options=("A", "B", "C", "D"),
            mode_code="QUICK_MIX_A1A2",
            source="FRIEND_CHALLENGE",
        ),
        energy_free=0,
        energy_paid=0,
        idempotent_replay=False,
    )


def _context(
    challenge: FriendChallenge,
    *,
    has_opponent: bool = True,
    is_creator: bool = True,
    next_round: int = 1,
) -> friend_challenges_rounds_state._FriendChallengeRoundContext:
    return friend_challenges_rounds_state._FriendChallengeRoundContext(
        challenge=challenge,
        has_opponent=has_opponent,
        is_creator=is_creator,
        next_round=next_round,
    )


@pytest.mark.asyncio
async def test_start_friend_challenge_round_returns_already_answered_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(total_rounds=1)
    context = _context(challenge, next_round=2)
    snapshot = _snapshot(challenge)

    async def _unexpected_lookup(*args, **kwargs):
        del args, kwargs
        pytest.fail("round session lookup should not happen after total rounds")

    monkeypatch.setattr(
        friend_challenges_rounds,
        "load_friend_challenge_round_context",
        _async_return(context),
    )
    monkeypatch.setattr(friend_challenges_rounds, "is_round_playable", lambda *_args: True)
    monkeypatch.setattr(
        friend_challenges_rounds.QuizSessionsRepo,
        "get_by_friend_challenge_round_user",
        _unexpected_lookup,
    )
    monkeypatch.setattr(
        friend_challenges_rounds,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: snapshot if challenge_row is challenge else None,
    )

    result = await friend_challenges_rounds.start_friend_challenge_round(
        _Session(),
        user_id=10,
        challenge_id=challenge.id,
        idempotency_key="idem-1",
        now_utc=NOW_UTC,
    )

    assert result == FriendChallengeRoundStartResult(
        snapshot=snapshot,
        start_result=None,
        waiting_for_opponent=True,
        already_answered_current_round=True,
    )


@pytest.mark.asyncio
async def test_start_friend_challenge_round_uses_existing_round_session_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    context = _context(challenge)
    existing_round_session = object()
    start_result = _start_result(question_id="q-existing")
    snapshot = _snapshot(challenge)
    captured: dict[str, object] = {}

    async def _fake_build_existing_round_start_result(*args, **kwargs):
        del args
        captured["kwargs"] = kwargs
        return start_result

    async def _unexpected_start_new_round_session(*args, **kwargs):
        del args, kwargs
        pytest.fail("new round session should not start when an existing round session is found")

    monkeypatch.setattr(
        friend_challenges_rounds,
        "load_friend_challenge_round_context",
        _async_return(context),
    )
    monkeypatch.setattr(
        friend_challenges_rounds.QuizSessionsRepo,
        "get_by_friend_challenge_round_user",
        _async_return(existing_round_session),
    )
    monkeypatch.setattr(
        friend_challenges_rounds,
        "build_existing_round_start_result",
        _fake_build_existing_round_start_result,
    )
    monkeypatch.setattr(
        friend_challenges_rounds,
        "start_new_round_session",
        _unexpected_start_new_round_session,
    )
    monkeypatch.setattr(
        friend_challenges_rounds,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: snapshot if challenge_row is challenge else None,
    )

    result = await friend_challenges_rounds.start_friend_challenge_round(
        _Session(),
        user_id=10,
        challenge_id=challenge.id,
        idempotency_key="idem-2",
        now_utc=NOW_UTC,
    )

    assert result == FriendChallengeRoundStartResult(
        snapshot=snapshot,
        start_result=start_result,
        waiting_for_opponent=False,
        already_answered_current_round=False,
    )
    assert captured["kwargs"] == {
        "existing_round_session": existing_round_session,
        "tournament_match_id": TOURNAMENT_MATCH_ID,
    }


@pytest.mark.asyncio
async def test_start_friend_challenge_round_starts_new_round_when_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    context = _context(challenge, next_round=2)
    start_result = _start_result(question_id="q-new")
    snapshot = _snapshot(challenge)
    captured: dict[str, object] = {}

    async def _fake_start_new_round_session(*args, **kwargs):
        del args
        captured["kwargs"] = kwargs
        return start_result

    async def _unexpected_build_existing_round_start_result(*args, **kwargs):
        del args, kwargs
        pytest.fail("existing round result should not be built without an existing round session")

    monkeypatch.setattr(
        friend_challenges_rounds,
        "load_friend_challenge_round_context",
        _async_return(context),
    )
    monkeypatch.setattr(
        friend_challenges_rounds.QuizSessionsRepo,
        "get_by_friend_challenge_round_user",
        _async_return(None),
    )
    monkeypatch.setattr(
        friend_challenges_rounds,
        "build_existing_round_start_result",
        _unexpected_build_existing_round_start_result,
    )
    monkeypatch.setattr(
        friend_challenges_rounds,
        "start_new_round_session",
        _fake_start_new_round_session,
    )
    monkeypatch.setattr(
        friend_challenges_rounds,
        "_build_friend_challenge_snapshot",
        lambda challenge_row: snapshot if challenge_row is challenge else None,
    )

    result = await friend_challenges_rounds.start_friend_challenge_round(
        _Session(),
        user_id=10,
        challenge_id=challenge.id,
        idempotency_key="idem-3",
        now_utc=NOW_UTC,
    )

    assert result == FriendChallengeRoundStartResult(
        snapshot=snapshot,
        start_result=start_result,
        waiting_for_opponent=False,
        already_answered_current_round=False,
    )
    assert captured["kwargs"] == {
        "challenge": challenge,
        "next_round": 2,
        "user_id": 10,
        "idempotency_key": "idem-3",
        "now_utc": NOW_UTC,
    }
