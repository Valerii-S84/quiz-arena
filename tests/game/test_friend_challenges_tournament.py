from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.game.sessions.service import friend_challenges_tournament
from app.game.sessions.types import FriendChallengeSnapshot
from tests.type_helpers import AsyncSessionStub, build_friend_challenge

NOW_UTC = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)
CHALLENGE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TOURNAMENT_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TOURNAMENT_MATCH_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


class _Session(AsyncSessionStub):
    pass


def _snapshot(*, challenge_id: UUID = CHALLENGE_ID) -> FriendChallengeSnapshot:
    return FriendChallengeSnapshot(
        challenge_id=challenge_id,
        invite_token="invite-token",
        challenge_type="DIRECT",
        mode_code="QUICK_MIX_A1A2",
        access_type="FREE",
        status="ACCEPTED",
        creator_user_id=101,
        opponent_user_id=202,
        current_round=1,
        total_rounds=5,
        creator_score=0,
        opponent_score=0,
        question_ids=("q-1", "q-2"),
    )


@pytest.mark.asyncio
async def test_create_tournament_match_friend_challenge_builds_question_plan_and_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_challenge = build_friend_challenge(status="ACCEPTED")
    captured: dict[str, object] = {}

    async def _fake_select_duel_question_ids(_session, **kwargs):
        captured["question_kwargs"] = kwargs
        return ["q-1", "q-2", "q-3"]

    async def _fake_create_friend_challenge_row(_session, **kwargs):
        captured["create_kwargs"] = kwargs
        return created_challenge

    monkeypatch.setattr(friend_challenges_tournament, "uuid4", lambda: CHALLENGE_ID)
    monkeypatch.setattr(
        friend_challenges_tournament,
        "resolve_duel_rounds",
        lambda **_kwargs: 5,
    )
    monkeypatch.setattr(
        friend_challenges_tournament,
        "select_duel_question_ids",
        _fake_select_duel_question_ids,
    )
    monkeypatch.setattr(
        friend_challenges_tournament,
        "_create_friend_challenge_row",
        _fake_create_friend_challenge_row,
    )
    monkeypatch.setattr(
        friend_challenges_tournament,
        "_build_friend_challenge_snapshot",
        lambda challenge: _snapshot(challenge_id=challenge.id),
    )

    result = await friend_challenges_tournament.create_tournament_match_friend_challenge(
        _Session(),
        creator_user_id=101,
        opponent_user_id=202,
        tournament_id=TOURNAMENT_ID,
        tournament_round_no=2,
        mode_code="QUICK_MIX_A1A2",
        total_rounds=7,
        tournament_match_id=TOURNAMENT_MATCH_ID,
        now_utc=NOW_UTC,
        preferred_levels_by_round=("A1", "A2"),
    )

    assert result == _snapshot(challenge_id=created_challenge.id)
    assert captured["question_kwargs"] == {
        "mode_code": "QUICK_MIX_A1A2",
        "total_rounds": 5,
        "now_utc": NOW_UTC,
        "challenge_seed": str(CHALLENGE_ID),
        "tournament_id": TOURNAMENT_ID,
        "tournament_round_no": 2,
        "preferred_levels_by_round": ("A1", "A2"),
    }
    assert captured["create_kwargs"] == {
        "challenge_id": CHALLENGE_ID,
        "creator_user_id": 101,
        "opponent_user_id": 202,
        "challenge_type": friend_challenges_tournament.DUEL_TYPE_DIRECT,
        "mode_code": "QUICK_MIX_A1A2",
        "access_type": "FREE",
        "total_rounds": 5,
        "now_utc": NOW_UTC,
        "question_ids": ["q-1", "q-2", "q-3"],
        "status": friend_challenges_tournament.DUEL_STATUS_ACCEPTED,
    }
    assert created_challenge.tournament_match_id == TOURNAMENT_MATCH_ID
    assert created_challenge.updated_at == NOW_UTC


@pytest.mark.asyncio
async def test_create_tournament_match_friend_challenge_overrides_expires_at_when_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_expires_at = NOW_UTC + timedelta(hours=6)
    explicit_expires_at = NOW_UTC + timedelta(minutes=30)
    created_challenge = build_friend_challenge(
        status="ACCEPTED",
        expires_at=original_expires_at,
    )

    monkeypatch.setattr(friend_challenges_tournament, "uuid4", lambda: CHALLENGE_ID)
    monkeypatch.setattr(
        friend_challenges_tournament,
        "resolve_duel_rounds",
        lambda **_kwargs: 5,
    )

    async def _fake_select_duel_question_ids(*_args, **_kwargs):
        return ["q-1", "q-2"]

    monkeypatch.setattr(
        friend_challenges_tournament,
        "select_duel_question_ids",
        _fake_select_duel_question_ids,
    )

    async def _fake_create_friend_challenge_row(_session, **_kwargs):
        return created_challenge

    monkeypatch.setattr(
        friend_challenges_tournament,
        "_create_friend_challenge_row",
        _fake_create_friend_challenge_row,
    )
    monkeypatch.setattr(
        friend_challenges_tournament,
        "_build_friend_challenge_snapshot",
        lambda challenge: _snapshot(challenge_id=challenge.id),
    )

    await friend_challenges_tournament.create_tournament_match_friend_challenge(
        _Session(),
        creator_user_id=101,
        opponent_user_id=202,
        mode_code="QUICK_MIX_A1A2",
        total_rounds=7,
        tournament_match_id=TOURNAMENT_MATCH_ID,
        now_utc=NOW_UTC,
        expires_at=explicit_expires_at,
        preferred_levels_by_round=None,
    )

    assert created_challenge.expires_at == explicit_expires_at
