from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from app.bot.handlers import start
from app.bot.texts.de import TEXTS_DE
from app.economy.offers.types import OfferSelection
from app.game.duels import rollout as duel_rollout
from app.game.sessions.errors import FriendChallengeExpiredError, FriendChallengeNotFoundError
from app.game.sessions.types import (
    FriendChallengeJoinResult,
    FriendChallengeRoundStartResult,
    FriendChallengeSnapshot,
    SessionQuestionView,
    StartSessionResult,
)
from tests.bot.helpers import DummyMessage, DummySessionLocal


class _StartMessage(DummyMessage):
    def __init__(
        self,
        *,
        text: str,
        from_user: SimpleNamespace | None,
        message_id: int = 100,
    ) -> None:
        super().__init__()
        self.text = text
        self.from_user = from_user
        self.message_id = message_id


class _StartMessageWithPhotoGuard(_StartMessage):
    def __init__(
        self,
        *,
        text: str,
        from_user: SimpleNamespace | None,
        message_id: int = 100,
    ) -> None:
        super().__init__(text=text, from_user=from_user, message_id=message_id)
        self.photo_calls = 0

    async def answer_photo(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        self.photo_calls += 1
        await super().answer(*args, **kwargs)


@pytest.fixture(autouse=True)
def _stub_start_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop_emit(*args, **kwargs):
        del args, kwargs
        return None

    monkeypatch.setattr(start.start_flow, "SessionLocal", DummySessionLocal())
    monkeypatch.setattr(start.start_flow, "emit_analytics_event", _noop_emit)


__all__ = [
    "Any",
    "DummyMessage",
    "DummySessionLocal",
    "FriendChallengeExpiredError",
    "FriendChallengeJoinResult",
    "FriendChallengeNotFoundError",
    "FriendChallengeRoundStartResult",
    "FriendChallengeSnapshot",
    "OfferSelection",
    "SessionQuestionView",
    "SimpleNamespace",
    "StartSessionResult",
    "TEXTS_DE",
    "UUID",
    "_StartMessage",
    "_StartMessageWithPhotoGuard",
    "_stub_start_runtime",
    "duel_rollout",
    "pytest",
    "start",
]
