from __future__ import annotations

import importlib
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal, engine
from app.game.tournaments import daily_cup_user_status
from app.game.tournaments.constants import (
    TOURNAMENT_FORMAT_QUICK_5,
    TOURNAMENT_STATUS_COMPLETED,
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_TYPE_DAILY_ARENA,
)
from app.game.tournaments.create_join import join_daily_cup_by_id
from tests.integration.friend_challenge_fixtures import _create_user
from tests.integration.test_private_tournament_service_integration import _ensure_tournament_schema

UTC = timezone.utc
_DEFAULT_TELEGRAM_USER_ID = object()


class DummyBotSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class DummyBot:
    def __init__(self) -> None:
        self.session = DummyBotSession()


class WorkerDummyPhoto:
    def __init__(self, file_id: str) -> None:
        self.file_id = file_id


class WorkerDummyMessage:
    def __init__(self, *, message_id: int, file_id: str | None = None) -> None:
        self.message_id = message_id
        self.photo = [WorkerDummyPhoto(file_id)] if file_id is not None else []


class RecordingWorkerBot(DummyBot):
    def __init__(self) -> None:
        super().__init__()
        self.send_messages: list[dict[str, Any]] = []
        self.edit_messages: list[dict[str, Any]] = []
        self.send_photos: list[dict[str, Any]] = []
        self._message_id = 1000
        self._file_id = 0

    async def send_message(self, **kwargs) -> WorkerDummyMessage:
        self.send_messages.append(kwargs)
        self._message_id += 1
        return WorkerDummyMessage(message_id=self._message_id)

    async def edit_message_text(self, **kwargs) -> None:
        self.edit_messages.append(kwargs)

    async def send_photo(self, **kwargs) -> WorkerDummyMessage:
        self.send_photos.append(kwargs)
        photo_payload = kwargs.get("photo")
        if isinstance(photo_payload, str):
            resolved_file_id = photo_payload
        else:
            self._file_id += 1
            resolved_file_id = f"worker-photo-{self._file_id}"
        return WorkerDummyMessage(message_id=0, file_id=resolved_file_id)


class _AsyncBeginContext:
    def __init__(self, session: object) -> None:
        self._session = session

    async def __aenter__(self) -> object:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        return None


def session_local_with_sessions(*sessions: object) -> SimpleNamespace:
    remaining = list(sessions)

    def _begin() -> _AsyncBeginContext:
        return _AsyncBeginContext(remaining.pop(0))

    return SimpleNamespace(begin=_begin)


def async_return(value):
    async def _inner(*args, **kwargs):
        del args, kwargs
        return value

    return _inner


def unique_seed(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


async def create_user(prefix: str) -> int:
    return await _create_user(unique_seed(prefix))


async def create_users(prefix: str, total: int) -> list[int]:
    return [await create_user(f"{prefix}_{idx}") for idx in range(total)]


def reload_daily_cup_config(
    monkeypatch: pytest.MonkeyPatch,
    env_value: str | None,
) -> ModuleType:
    if env_value is None:
        monkeypatch.delenv("DAILY_CUP_TOURNAMENT_TYPE", raising=False)
    else:
        monkeypatch.setenv("DAILY_CUP_TOURNAMENT_TYPE", env_value)
    import app.workers.tasks.daily_cup_config as daily_cup_config_module

    return importlib.reload(daily_cup_config_module)


def status_tournament(
    *,
    status: str,
    current_round: int = 0,
    tournament_type: str = TOURNAMENT_TYPE_DAILY_ARENA,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        type=tournament_type,
        status=status,
        current_round=current_round,
        registration_deadline=datetime(2026, 3, 1, 18, 0, tzinfo=UTC),
    )


def make_standing_row(
    *,
    user_id: int,
    place: int,
    score: str = "0",
    tie_break: str = "0",
    standings_message_id: int | None = None,
    proof_card_sent: bool = False,
    proof_card_file_id: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        user_id=user_id,
        place=place,
        participant=SimpleNamespace(
            user_id=user_id,
            score=Decimal(score),
            tie_break=Decimal(tie_break),
            standings_message_id=standings_message_id,
            proof_card_sent=proof_card_sent,
            proof_card_file_id=proof_card_file_id,
        ),
    )


def make_worker_user(
    *,
    user_id: int,
    telegram_user_id: int | None | object = _DEFAULT_TELEGRAM_USER_ID,
    username: str | None = None,
    first_name: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=user_id,
        telegram_user_id=(
            900000 + user_id
            if telegram_user_id is _DEFAULT_TELEGRAM_USER_ID
            else telegram_user_id
        ),
        username=username,
        first_name=first_name,
    )


def close_coroutine_with_name(coroutine: Coroutine[Any, Any, Any]) -> str:
    code_name = coroutine.cr_code.co_name
    coroutine.close()
    return str(code_name)


def close_coroutine_and_raise(coroutine: Coroutine[Any, Any, Any], exc: Exception) -> None:
    coroutine.close()
    raise exc


def patch_status_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        daily_cup_user_status,
        "_invite_open_at_utc",
        lambda *, now_utc: now_utc - timedelta(minutes=1),
    )
    monkeypatch.setattr(
        daily_cup_user_status,
        "_close_at_utc",
        lambda *, now_utc: now_utc + timedelta(hours=1),
    )


async def prepare_tournament_db() -> None:
    await engine.dispose()
    await _ensure_tournament_schema()


async def create_daily_tournament(
    *,
    tournament_type: str,
    now_utc: datetime,
    status: str = TOURNAMENT_STATUS_REGISTRATION,
    current_round: int = 0,
) -> UUID:
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.create(
            session,
            tournament=Tournament(
                id=uuid4(),
                type=tournament_type,
                created_by=None,
                name=(
                    "Daily Arena Cup"
                    if tournament_type == TOURNAMENT_TYPE_DAILY_ARENA
                    else "Daily Elimination Cup"
                ),
                status=status,
                format=TOURNAMENT_FORMAT_QUICK_5,
                max_participants=100,
                current_round=current_round,
                registration_deadline=now_utc + timedelta(hours=6),
                round_deadline=None,
                invite_code=uuid4().hex[:12],
                created_at=now_utc,
            ),
        )
        return tournament.id


async def create_completed_daily_arena(*, now_utc: datetime, user_ids: list[int]) -> str:
    tournament_id = await create_daily_tournament(
        tournament_type=TOURNAMENT_TYPE_DAILY_ARENA,
        now_utc=now_utc,
        status=TOURNAMENT_STATUS_COMPLETED,
        current_round=3,
    )
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        tournament.registration_deadline = now_utc
        for index, user_id in enumerate(user_ids):
            await TournamentParticipantsRepo.create_once(
                session,
                tournament_id=tournament_id,
                user_id=user_id,
                joined_at=now_utc + timedelta(minutes=index),
            )
    return str(tournament_id)


async def join_daily_users(*, tournament_id: UUID, user_ids: list[int], now_utc: datetime) -> None:
    async with SessionLocal.begin() as session:
        for user_id in user_ids:
            await join_daily_cup_by_id(
                session,
                user_id=user_id,
                tournament_id=tournament_id,
                now_utc=now_utc,
            )
