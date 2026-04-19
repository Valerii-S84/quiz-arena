from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.models.friend_challenges import FriendChallenge
from app.game.sessions.service import friend_challenges_followup_state
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class _Session(AsyncSessionStub):
    pass


def _challenge(
    *,
    status: str = "COMPLETED",
    creator_user_id: int = 101,
    opponent_user_id: int | None = 202,
) -> FriendChallenge:
    return build_friend_challenge(
        id=uuid4(),
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        status=status,
        expires_at=NOW_UTC + timedelta(minutes=15),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("initiator_user_id", "expected_opponent_user_id"),
    [(101, 202), (202, 101)],
    ids=["creator_initiator", "opponent_initiator"],
)
async def test_load_friend_challenge_followup_context_delegates_and_resolves_opponent(
    monkeypatch: pytest.MonkeyPatch,
    initiator_user_id: int,
    expected_opponent_user_id: int,
) -> None:
    challenge = _challenge()
    load_calls: list[dict[str, object]] = []

    async def _fake_load_followup_friend_challenge(*_args, **kwargs):
        load_calls.append(kwargs)
        return challenge

    monkeypatch.setattr(
        friend_challenges_followup_state,
        "load_followup_friend_challenge",
        _fake_load_followup_friend_challenge,
    )

    context = await friend_challenges_followup_state.load_friend_challenge_followup_context(
        _Session(),
        initiator_user_id=initiator_user_id,
        challenge_id=challenge.id,
        now_utc=NOW_UTC,
    )

    assert context == friend_challenges_followup_state.FriendChallengeFollowupContext(
        challenge=challenge,
        opponent_user_id=expected_opponent_user_id,
    )
    assert load_calls == [
        {
            "challenge_id": challenge.id,
            "initiator_user_id": initiator_user_id,
            "now_utc": NOW_UTC,
        }
    ]
