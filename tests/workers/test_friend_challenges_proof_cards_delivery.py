from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendPhoto

from app.workers.tasks.friend_challenges_proof_cards_context import (
    FriendChallengeProofCardRecipient,
    FriendChallengeProofCardsContext,
)
from app.workers.tasks.friend_challenges_proof_cards_delivery import (
    deliver_friend_challenge_proof_cards,
)

CHALLENGE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


class _Session:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _RecordingBot:
    def __init__(self) -> None:
        self.session = _Session()
        self.sent_photos: list[dict[str, object]] = []

    async def send_photo(self, **kwargs):
        self.sent_photos.append(kwargs)
        file_id = (
            kwargs["photo"] if isinstance(kwargs["photo"], str) else f"file-{len(self.sent_photos)}"
        )
        return SimpleNamespace(photo=[SimpleNamespace(file_id=file_id)])


class _BlockedBot(_RecordingBot):
    async def send_photo(self, **kwargs):
        del kwargs
        raise TelegramForbiddenError(
            method=SendPhoto(chat_id=1, photo="cached-file"),
            message="forbidden",
        )


def _context(*, cached_file_ids: tuple[str | None, str | None]):
    return FriendChallengeProofCardsContext(
        parsed_challenge_id=CHALLENGE_ID,
        challenge_id=str(CHALLENGE_ID),
        status="COMPLETED",
        creator_score=4,
        opponent_score=2,
        total_rounds=5,
        completed_at=datetime(2026, 3, 1, 18, 0, tzinfo=timezone.utc),
        creator_name="Max",
        opponent_name="Anna",
        recipients=[
            FriendChallengeProofCardRecipient("creator", 10, 90010, cached_file_ids[0]),
            FriendChallengeProofCardRecipient("opponent", 20, 90020, cached_file_ids[1]),
        ],
    )


def _keyboard(**kwargs):
    return {"keyboard": kwargs}


def _caption(**kwargs) -> str:
    return f"{kwargs['role']}:{kwargs['status']}"


@pytest.mark.asyncio
async def test_deliver_reuses_cached_file_ids_without_rendering() -> None:
    bot = _RecordingBot()

    result = await deliver_friend_challenge_proof_cards(
        context=_context(cached_file_ids=("creator-cache", "opponent-cache")),
        build_bot_fn=lambda: bot,
        build_keyboard_fn=_keyboard,
        build_caption_fn=_caption,
        render_card_fn=lambda **kwargs: pytest.fail(f"unexpected render: {kwargs}"),
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    assert result.sent == 2
    assert result.cached_reused == 2
    assert result.new_creator_file_id is None
    assert result.new_opponent_file_id is None
    assert [item["photo"] for item in bot.sent_photos] == ["creator-cache", "opponent-cache"]
    assert bot.session.closed is True


@pytest.mark.asyncio
async def test_deliver_renders_once_and_returns_new_file_ids() -> None:
    bot = _RecordingBot()
    render_calls: list[dict[str, object]] = []

    def _render(**kwargs) -> bytes:
        render_calls.append(kwargs)
        return b"png"

    result = await deliver_friend_challenge_proof_cards(
        context=_context(cached_file_ids=(None, None)),
        build_bot_fn=lambda: bot,
        build_keyboard_fn=_keyboard,
        build_caption_fn=_caption,
        render_card_fn=_render,
        logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
    )

    assert result.sent == 2
    assert result.cached_reused == 0
    assert result.new_creator_file_id == "file-1"
    assert result.new_opponent_file_id == "file-2"
    assert len(render_calls) == 1
    assert [item["caption"] for item in bot.sent_photos] == [
        "creator:COMPLETED",
        "opponent:COMPLETED",
    ]
    assert bot.session.closed is True


@pytest.mark.asyncio
async def test_deliver_handles_blocked_bot_and_closes_session() -> None:
    bot = _BlockedBot()
    warnings: list[dict[str, object]] = []

    result = await deliver_friend_challenge_proof_cards(
        context=_context(cached_file_ids=(None, None)),
        build_bot_fn=lambda: bot,
        build_keyboard_fn=_keyboard,
        build_caption_fn=_caption,
        render_card_fn=lambda **kwargs: b"png",
        logger=SimpleNamespace(
            warning=lambda event, **kwargs: warnings.append({"event": event, **kwargs})
        ),
    )

    assert result.sent == 0
    assert result.cached_reused == 0
    assert result.new_creator_file_id is None
    assert warnings == [
        {
            "event": "friend_challenge_proof_card_send_failed",
            "challenge_id": str(CHALLENGE_ID),
            "error_type": "TelegramForbiddenError",
        }
    ]
    assert bot.session.closed is True
