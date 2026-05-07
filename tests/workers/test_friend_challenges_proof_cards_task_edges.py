from __future__ import annotations

from uuid import UUID

import pytest

from app.workers.tasks import friend_challenges_proof_cards as cards
from app.workers.tasks.friend_challenges_proof_cards_context import (
    FriendChallengeProofCardRecipient,
    FriendChallengeProofCardsContext,
)
from app.workers.tasks.friend_challenges_proof_cards_delivery import (
    FriendChallengeProofCardsDeliveryResult,
)

CHALLENGE_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


class _AsyncBeginContext:
    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> object:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb


class _SessionFactory:
    def __init__(self, *sessions: object) -> None:
        self.sessions = list(sessions)

    def begin(self) -> _AsyncBeginContext:
        return _AsyncBeginContext(self.sessions.pop(0))


def _context() -> FriendChallengeProofCardsContext:
    return FriendChallengeProofCardsContext(
        parsed_challenge_id=CHALLENGE_ID,
        challenge_id=str(CHALLENGE_ID),
        status="COMPLETED",
        creator_score=4,
        opponent_score=2,
        total_rounds=7,
        completed_at=None,
        creator_name="Max",
        opponent_name="Anna",
        recipients=[FriendChallengeProofCardRecipient("creator", 10, 90010, "creator-cache")],
    )


@pytest.mark.asyncio
async def test_run_async_returns_empty_when_context_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _load_context(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(cards, "SessionLocal", _SessionFactory(object()))
    monkeypatch.setattr(cards, "load_friend_challenge_proof_cards_context", _load_context)
    monkeypatch.setattr(
        cards,
        "deliver_friend_challenge_proof_cards",
        lambda **kwargs: pytest.fail(f"unexpected delivery: {kwargs}"),
    )

    result = await cards.run_friend_challenge_proof_cards_async(challenge_id=str(CHALLENGE_ID))

    assert result == {"processed": 0, "sent": 0, "cached_reused": 0}


@pytest.mark.asyncio
async def test_run_async_skips_persistence_when_delivery_has_no_new_file_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _load_context(**kwargs):
        del kwargs
        return _context()

    async def _deliver(**kwargs):
        assert kwargs["context"].challenge_id == str(CHALLENGE_ID)
        return FriendChallengeProofCardsDeliveryResult(
            sent=1,
            cached_reused=1,
            new_creator_file_id=None,
            new_opponent_file_id=None,
        )

    async def _persist(**kwargs):
        raise AssertionError(f"unexpected persistence: {kwargs}")

    monkeypatch.setattr(cards, "SessionLocal", _SessionFactory("load-session"))
    monkeypatch.setattr(cards, "load_friend_challenge_proof_cards_context", _load_context)
    monkeypatch.setattr(cards, "deliver_friend_challenge_proof_cards", _deliver)
    monkeypatch.setattr(cards, "persist_friend_challenge_proof_card_file_ids", _persist)

    result = await cards.run_friend_challenge_proof_cards_async(challenge_id=str(CHALLENGE_ID))

    assert result == {"processed": 1, "sent": 1, "cached_reused": 1}


def test_is_celery_task_uses_type_module_prefix() -> None:
    class _CeleryTask:
        pass

    class _LocalTask:
        pass

    _CeleryTask.__module__ = "celery.local"
    _LocalTask.__module__ = "app.workers.tasks.friend_challenges_proof_cards"

    assert cards._is_celery_task(_CeleryTask()) is True
    assert cards._is_celery_task(_LocalTask()) is False
