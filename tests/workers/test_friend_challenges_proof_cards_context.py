from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.workers.tasks.friend_challenges_proof_cards_context import (
    FriendChallengeProofCardRecipient,
    load_friend_challenge_proof_cards_context,
)
from app.workers.tasks.friend_challenges_proof_cards_persistence import (
    persist_friend_challenge_proof_card_file_ids,
)

CHALLENGE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class _ChallengesRepo:
    def __init__(self, row: object | None) -> None:
        self.row = row
        self.calls: list[UUID] = []

    async def get_by_id_for_update(self, session, challenge_id: UUID):
        del session
        self.calls.append(challenge_id)
        return self.row


class _UsersRepo:
    def __init__(self, users: dict[int, object | None]) -> None:
        self.users = users

    async def get_by_id(self, session, user_id: int):
        del session
        return self.users.get(int(user_id))


def _challenge(
    *,
    status: str = "COMPLETED",
    creator_file_id: str | None = None,
    opponent_file_id: str | None = None,
):
    return SimpleNamespace(
        id=CHALLENGE_ID,
        status=status,
        creator_user_id=10,
        opponent_user_id=20,
        creator_score=4,
        opponent_score=2,
        total_rounds=5,
        completed_at=datetime(2026, 3, 1, 18, 0, tzinfo=timezone.utc),
        creator_proof_card_file_id=creator_file_id,
        opponent_proof_card_file_id=opponent_file_id,
    )


def _user(user_id: int, telegram_user_id: int):
    return SimpleNamespace(id=user_id, telegram_user_id=telegram_user_id)


def _label(*, user, fallback: str) -> str:
    return fallback if user is None else f"user-{user.id}"


@pytest.mark.asyncio
async def test_load_context_returns_both_recipients() -> None:
    context = await load_friend_challenge_proof_cards_context(
        session=object(),
        parsed_challenge_id=CHALLENGE_ID,
        requested_user_id=None,
        challenges_repo=_ChallengesRepo(_challenge(creator_file_id="creator-cache")),
        users_repo=_UsersRepo({10: _user(10, 90010), 20: _user(20, 90020)}),
        final_statuses=frozenset({"COMPLETED"}),
        resolve_user_label_fn=_label,
    )

    assert context is not None
    assert context.challenge_id == str(CHALLENGE_ID)
    assert context.creator_name == "user-10"
    assert context.opponent_name == "user-20"
    assert context.recipients == [
        FriendChallengeProofCardRecipient("creator", 10, 90010, "creator-cache"),
        FriendChallengeProofCardRecipient("opponent", 20, 90020, None),
    ]


@pytest.mark.asyncio
async def test_load_context_can_return_no_recipients_for_filtered_user() -> None:
    context = await load_friend_challenge_proof_cards_context(
        session=object(),
        parsed_challenge_id=CHALLENGE_ID,
        requested_user_id=999,
        challenges_repo=_ChallengesRepo(_challenge()),
        users_repo=_UsersRepo({10: _user(10, 90010), 20: _user(20, 90020)}),
        final_statuses=frozenset({"COMPLETED"}),
        resolve_user_label_fn=_label,
    )

    assert context is not None
    assert context.recipients == []


@pytest.mark.asyncio
async def test_load_context_skips_missing_or_non_final_challenge() -> None:
    missing_context = await load_friend_challenge_proof_cards_context(
        session=object(),
        parsed_challenge_id=CHALLENGE_ID,
        requested_user_id=None,
        challenges_repo=_ChallengesRepo(None),
        users_repo=_UsersRepo({}),
        final_statuses=frozenset({"COMPLETED"}),
        resolve_user_label_fn=_label,
    )
    draft_context = await load_friend_challenge_proof_cards_context(
        session=object(),
        parsed_challenge_id=CHALLENGE_ID,
        requested_user_id=None,
        challenges_repo=_ChallengesRepo(_challenge(status="ACCEPTED")),
        users_repo=_UsersRepo({}),
        final_statuses=frozenset({"COMPLETED"}),
        resolve_user_label_fn=_label,
    )

    assert missing_context is None
    assert draft_context is None


@pytest.mark.asyncio
async def test_persist_file_ids_sets_missing_values_without_overwrite() -> None:
    row = _challenge()
    repo = _ChallengesRepo(row)

    await persist_friend_challenge_proof_card_file_ids(
        session=object(),
        parsed_challenge_id=CHALLENGE_ID,
        challenges_repo=repo,
        new_creator_file_id="creator-new",
        new_opponent_file_id="opponent-new",
    )

    assert row.creator_proof_card_file_id == "creator-new"
    assert row.opponent_proof_card_file_id == "opponent-new"

    await persist_friend_challenge_proof_card_file_ids(
        session=object(),
        parsed_challenge_id=CHALLENGE_ID,
        challenges_repo=repo,
        new_creator_file_id="creator-later",
        new_opponent_file_id="opponent-later",
    )

    assert row.creator_proof_card_file_id == "creator-new"
    assert row.opponent_proof_card_file_id == "opponent-new"


@pytest.mark.asyncio
async def test_persist_file_ids_ignores_missing_challenge() -> None:
    repo = _ChallengesRepo(None)

    await persist_friend_challenge_proof_card_file_ids(
        session=object(),
        parsed_challenge_id=CHALLENGE_ID,
        challenges_repo=repo,
        new_creator_file_id="creator-new",
        new_opponent_file_id="opponent-new",
    )

    assert repo.calls == [CHALLENGE_ID]
