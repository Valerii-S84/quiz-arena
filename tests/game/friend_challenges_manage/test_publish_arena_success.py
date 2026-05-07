from typing import cast

import pytest

from app.db.models.arena_duels import ArenaAttempt, ArenaDuel
from app.db.repo.arena_duels_repo import ArenaActiveDuelRow, ArenaDuelsRepo
from app.game.friend_challenges.constants import DUEL_STATUS_CREATOR_DONE
from app.game.sessions.service import friend_challenges_manage

from .support import (
    NOW_UTC,
    SessionStub,
    arena_baseline_attempt,
    arena_duel_from_friend,
    async_return,
    challenge,
)


@pytest.mark.asyncio
async def test_publish_friend_challenge_to_arena_creates_active_duel_from_creator_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_challenge = challenge(
        status=DUEL_STATUS_CREATOR_DONE,
        creator_user_id=11,
        opponent_user_id=None,
    )
    created: dict[str, object] = {}

    async def fake_create_duel(*_args, **kwargs):
        created["duel"] = kwargs["duel"]
        return kwargs["duel"]

    async def fake_create_attempt(*_args, **kwargs):
        created["attempt"] = kwargs["attempt"]
        return kwargs["attempt"]

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(current_challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage, "_expire_friend_challenge_if_due", lambda **_kwargs: False
    )
    monkeypatch.setattr(
        ArenaDuelsRepo, "get_source_friend_duel_with_baseline_for_update", async_return(None)
    )
    monkeypatch.setattr(ArenaDuelsRepo, "create_duel", fake_create_duel)
    monkeypatch.setattr(ArenaDuelsRepo, "create_attempt", fake_create_attempt)
    monkeypatch.setattr(
        friend_challenges_manage.QuizSessionsRepo,
        "sum_completed_duration_ms_for_friend_challenge_user",
        async_return(48_000),
    )

    result = await friend_challenges_manage.publish_friend_challenge_to_arena(
        SessionStub(),
        user_id=11,
        friend_challenge_id=current_challenge.id,
        now_utc=NOW_UTC,
    )

    duel = cast(ArenaDuel, created["duel"])
    attempt = cast(ArenaAttempt, created["attempt"])
    assert duel.status == "ACTIVE"
    assert duel.source_friend_challenge_id == current_challenge.id
    assert duel.question_ids == current_challenge.question_ids
    assert duel.baseline_attempt_id == attempt.id
    assert attempt.score == 6
    assert attempt.time_ms == 48_000
    assert attempt.completed_at == NOW_UTC
    assert result.baseline_score == 6
    assert result.baseline_time_ms == 48_000


@pytest.mark.asyncio
async def test_publish_friend_challenge_to_arena_returns_existing_active_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_challenge = challenge(
        status=DUEL_STATUS_CREATOR_DONE,
        creator_user_id=11,
        opponent_user_id=None,
    )
    existing_duel = arena_duel_from_friend(challenge_id=current_challenge.id)
    existing_attempt = arena_baseline_attempt(duel_id=existing_duel.id)
    existing_duel.baseline_attempt_id = existing_attempt.id

    async def unexpected_create_duel(*_args, **_kwargs):
        pytest.fail("duplicate friend publish must not create another Arena duel")

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(current_challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage, "_expire_friend_challenge_if_due", lambda **_kwargs: False
    )
    monkeypatch.setattr(
        ArenaDuelsRepo,
        "get_source_friend_duel_with_baseline_for_update",
        async_return(ArenaActiveDuelRow(existing_duel, existing_attempt)),
    )
    monkeypatch.setattr(ArenaDuelsRepo, "create_duel", unexpected_create_duel)

    result = await friend_challenges_manage.publish_friend_challenge_to_arena(
        SessionStub(),
        user_id=11,
        friend_challenge_id=current_challenge.id,
        now_utc=NOW_UTC,
    )

    assert result.duel_id == existing_duel.id
    assert result.baseline_attempt_id == existing_attempt.id
    assert result.baseline_score == existing_attempt.score
    assert result.baseline_time_ms == existing_attempt.time_ms
