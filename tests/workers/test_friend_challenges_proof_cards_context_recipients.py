from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.workers.tasks.friend_challenges_proof_cards_context import (
    FriendChallengeProofCardRecipient,
    load_friend_challenge_proof_cards_context,
)

CHALLENGE_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


class _ChallengesRepo:
    def __init__(self, row: object) -> None:
        self.row = row

    async def get_by_id_for_update(self, session, challenge_id: UUID):
        del session, challenge_id
        return self.row


class _UsersRepo:
    def __init__(self, users: dict[int, object | None]) -> None:
        self.users = users

    async def get_by_id(self, session, user_id: int):
        del session
        return self.users.get(int(user_id))


def _challenge():
    return SimpleNamespace(
        id=CHALLENGE_ID,
        status="COMPLETED",
        creator_user_id=10,
        opponent_user_id=20,
        creator_score=4,
        opponent_score=2,
        total_rounds=7,
        completed_at=datetime(2026, 3, 1, 18, 0, tzinfo=timezone.utc),
        creator_proof_card_file_id="creator-cache",
        opponent_proof_card_file_id="opponent-cache",
    )


def _user(user_id: int, telegram_user_id: int):
    return SimpleNamespace(id=user_id, telegram_user_id=telegram_user_id)


def _label(*, user, fallback: str) -> str:
    return fallback if user is None else f"user-{user.id}"


@pytest.mark.asyncio
async def test_load_context_can_return_only_creator_recipient() -> None:
    context = await load_friend_challenge_proof_cards_context(
        session=object(),
        parsed_challenge_id=CHALLENGE_ID,
        requested_user_id=10,
        challenges_repo=_ChallengesRepo(_challenge()),
        users_repo=_UsersRepo({10: _user(10, 90010), 20: _user(20, 90020)}),
        final_statuses=frozenset({"COMPLETED"}),
        resolve_user_label_fn=_label,
    )

    assert context is not None
    assert context.recipients == [
        FriendChallengeProofCardRecipient("creator", 10, 90010, "creator-cache")
    ]


@pytest.mark.asyncio
async def test_load_context_can_return_only_opponent_recipient() -> None:
    context = await load_friend_challenge_proof_cards_context(
        session=object(),
        parsed_challenge_id=CHALLENGE_ID,
        requested_user_id=20,
        challenges_repo=_ChallengesRepo(_challenge()),
        users_repo=_UsersRepo({10: _user(10, 90010), 20: _user(20, 90020)}),
        final_statuses=frozenset({"COMPLETED"}),
        resolve_user_label_fn=_label,
    )

    assert context is not None
    assert context.recipients == [
        FriendChallengeProofCardRecipient("opponent", 20, 90020, "opponent-cache")
    ]
