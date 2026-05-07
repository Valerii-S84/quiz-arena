from types import SimpleNamespace

import pytest

from app.db.repo.arena_duels_repo import ArenaActiveDuelRow, ArenaDuelsRepo
from app.game.arena_duels.constants import ARENA_DUEL_STATUS_EXPIRED
from app.game.friend_challenges.constants import (
    DUEL_STATUS_COMPLETED,
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_WALKOVER,
    DUEL_TYPE_OPEN,
)
from app.game.sessions.errors import (
    FriendChallengeAccessError,
    FriendChallengeArenaPublishBaselineRequiredError,
)
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
async def test_publish_friend_challenge_to_arena_requests_baseline_for_empty_friend_duel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_challenge = challenge(status="PENDING", creator_user_id=11, opponent_user_id=None)
    current_challenge.creator_answered_round = 0
    current_challenge.creator_finished_at = None

    async def unexpected_create_duel(*_args, **_kwargs):
        pytest.fail("empty friend-duel must not create an Arena duel")

    monkeypatch.setattr(
        friend_challenges_manage.FriendChallengesRepo,
        "get_by_id_for_update",
        async_return(current_challenge),
    )
    monkeypatch.setattr(
        friend_challenges_manage, "_expire_friend_challenge_if_due", lambda **_kwargs: False
    )
    monkeypatch.setattr(ArenaDuelsRepo, "create_duel", unexpected_create_duel)

    with pytest.raises(FriendChallengeArenaPublishBaselineRequiredError):
        await friend_challenges_manage.publish_friend_challenge_to_arena(
            SessionStub(),
            user_id=11,
            friend_challenge_id=current_challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
async def test_publish_friend_challenge_to_arena_rejects_expired_duplicate_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_challenge = challenge(
        status=DUEL_STATUS_CREATOR_DONE,
        creator_user_id=11,
        opponent_user_id=None,
    )
    existing_duel = arena_duel_from_friend(
        challenge_id=current_challenge.id,
        status=ARENA_DUEL_STATUS_EXPIRED,
    )
    existing_attempt = arena_baseline_attempt(duel_id=existing_duel.id)
    existing_duel.baseline_attempt_id = existing_attempt.id

    async def unexpected_create_duel(*_args, **_kwargs):
        pytest.fail("expired duplicate publish must be denied, not recreated")

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

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_manage.publish_friend_challenge_to_arena(
            SessionStub(),
            user_id=11,
            friend_challenge_id=current_challenge.id,
            now_utc=NOW_UTC,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "current_challenge",
    [
        challenge(status=DUEL_STATUS_CREATOR_DONE, creator_user_id=11, opponent_user_id=22),
        challenge(status=DUEL_STATUS_COMPLETED, creator_user_id=11, opponent_user_id=None),
        challenge(status=DUEL_STATUS_WALKOVER, creator_user_id=11, opponent_user_id=None),
        challenge(
            status=DUEL_STATUS_CREATOR_DONE,
            creator_user_id=11,
            opponent_user_id=None,
            challenge_type=DUEL_TYPE_OPEN,
        ),
    ],
)
async def test_publish_friend_challenge_to_arena_rejects_unclean_server_state(
    monkeypatch: pytest.MonkeyPatch,
    current_challenge: SimpleNamespace,
) -> None:
    async def unexpected_source_lookup(*_args, **_kwargs):
        pytest.fail("unclean friend-duel state must not reach Arena lookup")

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
        unexpected_source_lookup,
    )

    with pytest.raises(FriendChallengeAccessError):
        await friend_challenges_manage.publish_friend_challenge_to_arena(
            SessionStub(),
            user_id=11,
            friend_challenge_id=current_challenge.id,
            now_utc=NOW_UTC,
        )
