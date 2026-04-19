from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.game.sessions.service import friend_challenges_expiry
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _challenge(**overrides: object):
    payload: dict[str, object] = {
        "creator_user_id": 101,
        "opponent_user_id": 202,
        "status": "ACCEPTED",
        "total_rounds": 5,
        "creator_score": 3,
        "opponent_score": 2,
        "creator_answered_round": 0,
        "opponent_answered_round": 0,
        "expires_at": NOW_UTC - timedelta(minutes=1),
    }
    payload.update(overrides)
    return build_friend_challenge(**payload)


@pytest.mark.asyncio
async def test_emit_friend_challenge_expired_event_delegates_to_analytics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    challenge = _challenge()
    captured: list[dict[str, object]] = []

    async def _fake_emit(session, **kwargs):
        del session
        captured.append(kwargs)

    monkeypatch.setattr(
        friend_challenges_expiry,
        "_emit_friend_challenge_expired_event_analytics",
        _fake_emit,
    )

    await friend_challenges_expiry._emit_friend_challenge_expired_event(
        _Session(),
        challenge=challenge,
        happened_at=NOW_UTC,
        source="BOT",
    )

    assert captured == [
        {
            "challenge": challenge,
            "happened_at": NOW_UTC,
            "source": "BOT",
        }
    ]


def test_expire_friend_challenge_if_due_returns_false_for_future_deadline() -> None:
    challenge = _challenge(expires_at=NOW_UTC + timedelta(minutes=1))

    expired = friend_challenges_expiry._expire_friend_challenge_if_due(
        challenge=challenge,
        now_utc=NOW_UTC,
    )

    assert expired is False
    assert challenge.status == "ACCEPTED"


def test_expire_friend_challenge_if_due_marks_pending_as_expired() -> None:
    challenge = _challenge(status="PENDING", winner_user_id=101)

    expired = friend_challenges_expiry._expire_friend_challenge_if_due(
        challenge=challenge,
        now_utc=NOW_UTC,
    )

    assert expired is True
    assert challenge.status == "EXPIRED"
    assert challenge.winner_user_id is None
    assert challenge.completed_at == NOW_UTC
    assert challenge.updated_at == NOW_UTC


@pytest.mark.parametrize(
    ("challenge", "expected_winner", "expected_creator_score", "expected_opponent_score"),
    [
        (_challenge(creator_answered_round=5), 101, 3, 0),
        (_challenge(opponent_answered_round=5), 202, 0, 2),
        (_challenge(creator_answered_round=5, opponent_answered_round=5), None, 0, 0),
    ],
    ids=["creator_walkover", "opponent_walkover", "mutual_timeout"],
)
def test_expire_friend_challenge_if_due_marks_joined_duel_walkover(
    challenge,
    expected_winner: int | None,
    expected_creator_score: int,
    expected_opponent_score: int,
) -> None:
    expired = friend_challenges_expiry._expire_friend_challenge_if_due(
        challenge=challenge,
        now_utc=NOW_UTC,
    )

    assert expired is True
    assert challenge.status == "WALKOVER"
    assert challenge.winner_user_id == expected_winner
    assert challenge.creator_score == expected_creator_score
    assert challenge.opponent_score == expected_opponent_score
    assert challenge.completed_at == NOW_UTC
    assert challenge.updated_at == NOW_UTC
