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

CHALLENGE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


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


def _context(*, recipients: list[FriendChallengeProofCardRecipient]):
    return FriendChallengeProofCardsContext(
        parsed_challenge_id=CHALLENGE_ID,
        challenge_id=str(CHALLENGE_ID),
        status="COMPLETED",
        creator_score=4,
        opponent_score=2,
        total_rounds=5,
        completed_at=None,
        creator_name="Max",
        opponent_name="Anna",
        recipients=recipients,
    )


def _close_coroutine_with_name(coroutine) -> str:
    code_name = coroutine.cr_code.co_name
    coroutine.close()
    return str(code_name)


def _close_coroutine_and_raise(coroutine, exc: Exception) -> None:
    coroutine.close()
    raise exc


@pytest.mark.asyncio
async def test_run_async_returns_empty_for_invalid_challenge_id() -> None:
    result = await cards.run_friend_challenge_proof_cards_async(
        challenge_id="not-a-uuid",
    )

    assert result == {"processed": 0, "sent": 0, "cached_reused": 0}


@pytest.mark.asyncio
async def test_run_async_counts_context_with_no_recipients(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _load_context(**kwargs):
        del kwargs
        return _context(recipients=[])

    monkeypatch.setattr(cards, "SessionLocal", _SessionFactory(object()))
    monkeypatch.setattr(cards, "load_friend_challenge_proof_cards_context", _load_context)
    monkeypatch.setattr(
        cards,
        "deliver_friend_challenge_proof_cards",
        lambda **kwargs: pytest.fail(f"unexpected delivery: {kwargs}"),
    )

    result = await cards.run_friend_challenge_proof_cards_async(
        challenge_id=str(CHALLENGE_ID),
    )

    assert result == {"processed": 1, "sent": 0, "cached_reused": 0}


@pytest.mark.asyncio
async def test_run_async_delivers_and_persists_new_file_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: list[dict[str, object]] = []

    async def _load_context(**kwargs):
        return _context(recipients=[FriendChallengeProofCardRecipient("creator", 10, 90010, None)])

    async def _deliver(**kwargs):
        assert kwargs["context"].challenge_id == str(CHALLENGE_ID)
        return FriendChallengeProofCardsDeliveryResult(
            sent=1,
            cached_reused=0,
            new_creator_file_id="creator-new",
            new_opponent_file_id=None,
        )

    async def _persist(**kwargs):
        persisted.append(kwargs)

    monkeypatch.setattr(cards, "SessionLocal", _SessionFactory("load-session", "persist-session"))
    monkeypatch.setattr(cards, "load_friend_challenge_proof_cards_context", _load_context)
    monkeypatch.setattr(cards, "deliver_friend_challenge_proof_cards", _deliver)
    monkeypatch.setattr(cards, "persist_friend_challenge_proof_card_file_ids", _persist)

    result = await cards.run_friend_challenge_proof_cards_async(
        challenge_id=str(CHALLENGE_ID),
    )

    assert result == {"processed": 1, "sent": 1, "cached_reused": 0}
    assert persisted[0]["session"] == "persist-session"
    assert persisted[0]["parsed_challenge_id"] == CHALLENGE_ID
    assert persisted[0]["challenges_repo"] is cards.FriendChallengesRepo
    assert persisted[0]["new_creator_file_id"] == "creator-new"
    assert persisted[0]["new_opponent_file_id"] is None


def test_enqueue_paths_and_task_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    enqueued: dict[str, object] = {}

    monkeypatch.setattr(cards, "_is_celery_task", lambda task: True)
    monkeypatch.setattr(
        cards.run_friend_challenge_proof_cards,
        "delay",
        lambda **kwargs: enqueued.setdefault("delay", kwargs),
    )
    cards.enqueue_friend_challenge_proof_cards(
        challenge_id="duel-celery",
        user_id=7,
    )
    assert enqueued["delay"] == {"challenge_id": "duel-celery", "user_id": 7}

    monkeypatch.setattr(cards, "_is_celery_task", lambda task: False)
    monkeypatch.setattr(
        cards,
        "run_async_job",
        lambda coroutine: enqueued.setdefault("direct", _close_coroutine_with_name(coroutine)),
    )
    cards.enqueue_friend_challenge_proof_cards(
        challenge_id="duel-direct",
    )
    assert enqueued["direct"] == "run_friend_challenge_proof_cards_async"

    warnings: list[dict[str, object]] = []
    monkeypatch.setattr(
        cards,
        "run_async_job",
        lambda coroutine: _close_coroutine_and_raise(coroutine, RuntimeError("boom")),
    )
    monkeypatch.setattr(
        cards.logger,
        "warning",
        lambda event, **kwargs: warnings.append({"event": event, **kwargs}),
    )
    cards.enqueue_friend_challenge_proof_cards(
        challenge_id="duel-failed",
    )
    assert warnings == [
        {
            "event": "friend_challenge_proof_card_enqueue_failed",
            "challenge_id": "duel-failed",
            "error_type": "RuntimeError",
        }
    ]

    monkeypatch.setattr(
        cards,
        "run_async_job",
        lambda coroutine: {"wrapped": _close_coroutine_with_name(coroutine)},
    )
    wrapped = cards.run_friend_challenge_proof_cards(challenge_id="duel-wrapper")
    assert wrapped == {"wrapped": "run_friend_challenge_proof_cards_async"}
