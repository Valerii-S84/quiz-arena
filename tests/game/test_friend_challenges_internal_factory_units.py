from __future__ import annotations

from uuid import uuid4

import pytest

from app.game.sessions.service import friend_challenges_internal_factory
from tests.game.friend_challenges_unit_support import NOW_UTC, Session, challenge


@pytest.mark.asyncio
async def test_resolve_friend_challenge_access_type_delegates_to_duel_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def _fake_resolve(_session, **kwargs):
        calls.append(kwargs)
        return "FREE"

    monkeypatch.setattr(
        friend_challenges_internal_factory.DuelLimitService,
        "resolve_friend_create_access_type",
        _fake_resolve,
    )

    result = await friend_challenges_internal_factory._resolve_friend_challenge_access_type(
        Session(),
        creator_user_id=11,
        now_utc=NOW_UTC,
    )

    assert result == "FREE"
    assert calls == [{"creator_user_id": 11, "now_utc": NOW_UTC}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected_expires_helper"),
    [
        ("PENDING", "_friend_challenge_expires_at"),
        ("ACCEPTED", "_friend_challenge_expires_at_accepted"),
    ],
)
async def test_create_friend_challenge_row_uses_expected_expiry_rule(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    expected_expires_helper: str,
) -> None:
    created = []
    challenge_id = uuid4()

    monkeypatch.setattr(
        friend_challenges_internal_factory,
        "_friend_challenge_expires_at",
        lambda **_kwargs: "pending-expiry",
    )
    monkeypatch.setattr(
        friend_challenges_internal_factory,
        "_friend_challenge_expires_at_accepted",
        lambda **_kwargs: "accepted-expiry",
    )

    async def _fake_create(_session, *, challenge):
        created.append(challenge)
        return challenge

    monkeypatch.setattr(
        friend_challenges_internal_factory.FriendChallengesRepo,
        "create",
        _fake_create,
    )

    result = await friend_challenges_internal_factory._create_friend_challenge_row(
        Session(),
        challenge_id=challenge_id,
        creator_user_id=11,
        opponent_user_id=22,
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        total_rounds=0,
        now_utc=NOW_UTC,
        question_ids=["q-1"],
        status=status,
        series_game_number=0,
        series_best_of=0,
    )

    assert result.id == challenge_id
    assert result.total_rounds == 1
    assert result.series_game_number == 1
    assert result.series_best_of == 1
    assert result.expires_at == ("accepted-expiry" if status == "ACCEPTED" else "pending-expiry")
    assert created


def test_build_friend_challenge_snapshot_copies_core_fields() -> None:
    row = challenge(status="CREATOR_DONE", question_ids=["q-1", "q-2"], tournament_match_id=uuid4())

    snapshot = friend_challenges_internal_factory._build_friend_challenge_snapshot(row)

    assert snapshot.challenge_id == row.id
    assert snapshot.status == "CREATOR_DONE"
    assert snapshot.question_ids == ("q-1", "q-2")
    assert snapshot.tournament_match_id == row.tournament_match_id
