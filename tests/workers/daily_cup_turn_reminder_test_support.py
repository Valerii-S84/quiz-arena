from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage


class DummyBotSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class RecordingBot:
    def __init__(
        self,
        *,
        forbidden_chat_id: int | None = None,
        failing_chat_id: int | None = None,
    ) -> None:
        self.session = DummyBotSession()
        self.forbidden_chat_id = forbidden_chat_id
        self.failing_chat_id = failing_chat_id
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, **kwargs) -> None:
        chat_id = int(kwargs["chat_id"])
        if self.forbidden_chat_id is not None and chat_id == self.forbidden_chat_id:
            raise TelegramForbiddenError(
                method=SendMessage(chat_id=chat_id, text="x"),
                message="forbidden",
            )
        if self.failing_chat_id is not None and chat_id == self.failing_chat_id:
            raise RuntimeError("boom")
        self.messages.append(kwargs)


class AsyncBeginContext:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        return None


def session_local_with_sessions(*sessions: object) -> SimpleNamespace:
    remaining = list(sessions)

    def _begin() -> AsyncBeginContext:
        return AsyncBeginContext(remaining.pop(0))

    return SimpleNamespace(begin=_begin)


def reminder_challenge(
    *,
    challenge_id: UUID,
    creator_user_id: int,
    opponent_user_id: int,
    status: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=challenge_id,
        creator_user_id=creator_user_id,
        opponent_user_id=opponent_user_id,
        status=status,
        expires_last_chance_notified_at=None,
        updated_at=None,
    )


def reminder_candidate(
    *,
    tournament_id: UUID,
    deadline: datetime,
    challenge: SimpleNamespace,
) -> tuple[SimpleNamespace, SimpleNamespace]:
    return (
        SimpleNamespace(tournament_id=tournament_id, deadline=deadline),
        challenge,
    )
