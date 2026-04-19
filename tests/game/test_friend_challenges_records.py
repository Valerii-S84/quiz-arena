from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.game.sessions.service import friend_challenges_records
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
GENERATED_CHALLENGE_ID = UUID("11111111-1111-1111-1111-111111111111")
INVITE_TOKEN_UUID = UUID("22222222-2222-2222-2222-222222222222")
EXPLICIT_CHALLENGE_ID = UUID("33333333-3333-3333-3333-333333333333")


class _Session(AsyncSessionStub):
    pass


@pytest.mark.asyncio
async def test_create_friend_challenge_row_uses_pending_ttl_and_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_rows: list[object] = []
    generated_values = iter([GENERATED_CHALLENGE_ID, INVITE_TOKEN_UUID])

    async def _fake_create(session, *, challenge):
        del session
        created_rows.append(challenge)
        return challenge

    monkeypatch.setattr(friend_challenges_records, "uuid4", lambda: next(generated_values))
    monkeypatch.setattr(
        friend_challenges_records.FriendChallengesRepo,
        "create",
        _fake_create,
    )

    challenge = await friend_challenges_records._create_friend_challenge_row(
        _Session(),
        creator_user_id=101,
        opponent_user_id=None,
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        total_rounds=5,
        now_utc=NOW_UTC,
        question_ids=["q-1", "q-2"],
    )

    assert created_rows == [challenge]
    assert challenge.id == GENERATED_CHALLENGE_ID
    assert challenge.invite_token == INVITE_TOKEN_UUID.hex
    assert challenge.status == "PENDING"
    assert challenge.total_rounds == 5
    assert challenge.series_game_number == 1
    assert challenge.series_best_of == 1
    assert challenge.question_ids == ["q-1", "q-2"]
    assert challenge.expires_at == NOW_UTC + timedelta(
        seconds=friend_challenges_records.DUEL_PENDING_TTL_SECONDS
    )


@pytest.mark.asyncio
async def test_create_friend_challenge_row_normalizes_accepted_series_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_rows: list[object] = []

    async def _fake_create(session, *, challenge):
        del session
        created_rows.append(challenge)
        return challenge

    monkeypatch.setattr(friend_challenges_records, "uuid4", lambda: INVITE_TOKEN_UUID)
    monkeypatch.setattr(
        friend_challenges_records.FriendChallengesRepo,
        "create",
        _fake_create,
    )

    challenge = await friend_challenges_records._create_friend_challenge_row(
        _Session(),
        challenge_id=EXPLICIT_CHALLENGE_ID,
        creator_user_id=101,
        opponent_user_id=202,
        mode_code="QUICK_MIX_A1A2",
        access_type="PAID_TICKET",
        total_rounds=0,
        now_utc=NOW_UTC,
        series_game_number=0,
        series_best_of=0,
        status="ACCEPTED",
    )

    assert created_rows == [challenge]
    assert challenge.id == EXPLICIT_CHALLENGE_ID
    assert challenge.total_rounds == 1
    assert challenge.series_game_number == 1
    assert challenge.series_best_of == 1
    assert challenge.status == "ACCEPTED"
    assert challenge.expires_at == NOW_UTC + timedelta(
        seconds=friend_challenges_records.DUEL_ACCEPTED_TTL_SECONDS
    )


def test_build_friend_challenge_snapshot_maps_model_fields() -> None:
    challenge = build_friend_challenge(
        id=EXPLICIT_CHALLENGE_ID,
        invite_token="invite-token",
        creator_user_id=101,
        opponent_user_id=202,
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        question_ids=["q-1", "q-2"],
        current_round=2,
        total_rounds=7,
        series_game_number=3,
        series_best_of=5,
        creator_score=4,
        opponent_score=3,
        winner_user_id=101,
        expires_at=NOW_UTC + timedelta(minutes=10),
    )

    snapshot = friend_challenges_records._build_friend_challenge_snapshot(challenge)

    assert snapshot.challenge_id == EXPLICIT_CHALLENGE_ID
    assert snapshot.invite_token == "invite-token"
    assert snapshot.creator_user_id == 101
    assert snapshot.opponent_user_id == 202
    assert snapshot.question_ids == ("q-1", "q-2")
    assert snapshot.current_round == 2
    assert snapshot.total_rounds == 7
    assert snapshot.series_game_number == 3
    assert snapshot.series_best_of == 5
    assert snapshot.creator_score == 4
    assert snapshot.opponent_score == 3
    assert snapshot.winner_user_id == 101
