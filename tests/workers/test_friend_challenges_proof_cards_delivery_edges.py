from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.workers.tasks.friend_challenges_proof_cards_context import (
    FriendChallengeProofCardRecipient,
    FriendChallengeProofCardsContext,
)
from app.workers.tasks.friend_challenges_proof_cards_delivery import (
    deliver_friend_challenge_proof_cards,
)

CHALLENGE_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


class _Session:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _QueuedBot:
    def __init__(self, *responses: object) -> None:
        self.session = _Session()
        self.responses = list(responses)
        self.sent_photos: list[dict[str, object]] = []

    async def send_photo(self, **kwargs):
        self.sent_photos.append(kwargs)
        return self.responses.pop(0)


def _context(
    *, recipients: list[FriendChallengeProofCardRecipient]
) -> FriendChallengeProofCardsContext:
    return FriendChallengeProofCardsContext(
        parsed_challenge_id=CHALLENGE_ID,
        challenge_id=str(CHALLENGE_ID),
        status="COMPLETED",
        creator_score=4,
        opponent_score=2,
        total_rounds=7,
        completed_at=datetime(2026, 3, 1, 18, 0, tzinfo=timezone.utc),
        creator_name="Max",
        opponent_name="Anna",
        recipients=recipients,
    )


@pytest.mark.asyncio
async def test_deliver_reuses_creator_cache_and_renders_only_for_uncached_opponent() -> None:
    bot = _QueuedBot(
        SimpleNamespace(photo=[SimpleNamespace(file_id="creator-cache")]),
        SimpleNamespace(photo=[SimpleNamespace(file_id="opponent-new")]),
    )
    render_calls: list[dict[str, object]] = []

    def _render(**kwargs) -> bytes:
        render_calls.append(kwargs)
        return b"png"

    result = await deliver_friend_challenge_proof_cards(
        context=_context(
            recipients=[
                FriendChallengeProofCardRecipient("creator", 10, 90010, "creator-cache"),
                FriendChallengeProofCardRecipient("opponent", 20, 90020, None),
            ]
        ),
        build_bot_fn=lambda: bot,
        build_keyboard_fn=lambda **kwargs: kwargs,
        build_caption_fn=lambda **kwargs: kwargs["role"],
        render_card_fn=_render,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    assert result.sent == 2
    assert result.cached_reused == 1
    assert result.new_creator_file_id is None
    assert result.new_opponent_file_id == "opponent-new"
    assert len(render_calls) == 1
    assert bot.session.closed is True


@pytest.mark.asyncio
async def test_deliver_handles_sent_photo_without_returned_file_id() -> None:
    bot = _QueuedBot(SimpleNamespace(photo=[]))

    result = await deliver_friend_challenge_proof_cards(
        context=_context(
            recipients=[FriendChallengeProofCardRecipient("creator", 10, 90010, None)]
        ),
        build_bot_fn=lambda: bot,
        build_keyboard_fn=lambda **kwargs: kwargs,
        build_caption_fn=lambda **kwargs: kwargs["role"],
        render_card_fn=lambda **kwargs: b"png",
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    assert result.sent == 1
    assert result.cached_reused == 0
    assert result.new_creator_file_id is None
    assert result.new_opponent_file_id is None
    assert bot.session.closed is True
