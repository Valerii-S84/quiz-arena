from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import Table

from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournament_round_scores import TournamentRoundScore
from app.db.models.tournaments import Tournament
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal, engine
from app.game.tournaments.service import (
    create_private_tournament,
    join_private_tournament_by_code,
    start_private_tournament,
)
from app.workers.tasks import tournaments_async, tournaments_messaging
from tests.integration.friend_challenge_fixtures import (
    _create_user,
    _seed_friend_challenge_questions,
)
from tests.integration.tournament_deadlock_test_support import run_with_deadlock_retry
from tests.type_helpers import as_any_dict

UTC = timezone.utc


class _DummyBotSession:
    async def close(self) -> None:
        return None


class _DummyPhoto:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id


class _DummyMessage:
    def __init__(self, *, message_id: int, file_id: str | None = None) -> None:
        self.message_id = message_id
        self.photo = [_DummyPhoto(file_id)] if file_id is not None else []


class _DummyWorkerBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()
        self.send_messages: list[dict[str, Any]] = []
        self.edit_messages: list[dict[str, Any]] = []
        self.send_photos: list[dict[str, Any]] = []
        self._message_id = 1000
        self._file_id = 0

    async def get_me(self):
        return type("BotMe", (), {"username": "quizarenabot"})()

    async def send_message(self, **kwargs: Any) -> _DummyMessage:
        self.send_messages.append(kwargs)
        self._message_id += 1
        return _DummyMessage(message_id=self._message_id)

    async def edit_message_text(self, **kwargs: Any) -> None:
        self.edit_messages.append(kwargs)

    async def send_photo(self, **kwargs: Any) -> _DummyMessage:
        self.send_photos.append(kwargs)
        photo_payload = kwargs.get("photo")
        if isinstance(photo_payload, str):
            resolved_file_id = photo_payload
        else:
            self._file_id += 1
            resolved_file_id = f"tournament-photo-{self._file_id}"
        return _DummyMessage(message_id=0, file_id=resolved_file_id)


async def _ensure_tournament_schema() -> None:
    round_scores_table = cast(Table, TournamentRoundScore.__table__)
    matches_table = cast(Table, TournamentMatch.__table__)
    participants_table = cast(Table, TournamentParticipant.__table__)
    tournaments_table = cast(Table, Tournament.__table__)

    async def _reset_schema() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(round_scores_table.drop, checkfirst=True)
            await conn.run_sync(matches_table.drop, checkfirst=True)
            await conn.run_sync(participants_table.drop, checkfirst=True)
            await conn.run_sync(tournaments_table.drop, checkfirst=True)
            await conn.run_sync(tournaments_table.create, checkfirst=True)
            await conn.run_sync(participants_table.create, checkfirst=True)
            await conn.run_sync(matches_table.create, checkfirst=True)
            await conn.run_sync(round_scores_table.create, checkfirst=True)

    await engine.dispose()
    await run_with_deadlock_retry(_reset_schema)


__all__ = [
    "Any",
    "FriendChallengesRepo",
    "SessionLocal",
    "Table",
    "Tournament",
    "TournamentMatch",
    "TournamentMatchesRepo",
    "TournamentParticipant",
    "TournamentParticipantsRepo",
    "TournamentRoundScore",
    "TournamentsRepo",
    "UTC",
    "UUID",
    "_DummyBotSession",
    "_DummyMessage",
    "_DummyPhoto",
    "_DummyWorkerBot",
    "_create_user",
    "_ensure_tournament_schema",
    "_seed_friend_challenge_questions",
    "as_any_dict",
    "cast",
    "create_private_tournament",
    "datetime",
    "engine",
    "join_private_tournament_by_code",
    "pytest",
    "run_with_deadlock_retry",
    "start_private_tournament",
    "timedelta",
    "timezone",
    "tournaments_async",
    "tournaments_messaging",
]
