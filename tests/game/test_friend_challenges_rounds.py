from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.service import (
    friend_challenges_rounds,
    friend_challenges_rounds_start_state,
    friend_challenges_rounds_state,
)
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


def _start_state(
    challenge: FriendChallenge,
    *,
    start_result: StartSessionResult | None,
    waiting_for_opponent: bool,
    already_answered_current_round: bool,
) -> friend_challenges_rounds_start_state.FriendChallengeRoundStartState:
    return friend_challenges_rounds_start_state.FriendChallengeRoundStartState(
        context=friend_challenges_rounds_state._FriendChallengeRoundContext(
            challenge=challenge,
            has_opponent=challenge.opponent_user_id is not None,
            is_creator=True,
            next_round=challenge.current_round,
        ),
        start_result=start_result,
        waiting_for_opponent=waiting_for_opponent,
        already_answered_current_round=already_answered_current_round,
    )


@pytest.mark.asyncio
async def test_start_friend_challenge_round_delegates_to_round_start_state_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge(total_rounds=1)
    start_state = _start_state(
        challenge,
        start_result=None,
        waiting_for_opponent=True,
        already_answered_current_round=True,
    )
    snapshot = _snapshot(challenge)
    load_calls: list[dict[str, object]] = []

    async def _fake_load_round_start_state(*_args, **kwargs):
        load_calls.append(kwargs)
        return start_state

    monkeypatch.setattr(
        friend_challenges_rounds,
        "load_friend_challenge_round_start_state",
        _fake_load_round_start_state,
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
    assert load_calls == [
        {
            "user_id": 10,
            "challenge_id": challenge.id,
            "idempotency_key": "idem-1",
            "now_utc": NOW_UTC,
        }
    ]


@pytest.mark.asyncio
async def test_start_friend_challenge_round_builds_result_from_loaded_start_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    start_result = _start_result(question_id="q-existing")
    start_state = _start_state(
        challenge,
        start_result=start_result,
        waiting_for_opponent=False,
        already_answered_current_round=False,
    )
    snapshot = _snapshot(challenge)

    async def _fake_load_round_start_state(*_args, **_kwargs):
        return start_state

    monkeypatch.setattr(
        friend_challenges_rounds,
        "load_friend_challenge_round_start_state",
        _fake_load_round_start_state,
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
