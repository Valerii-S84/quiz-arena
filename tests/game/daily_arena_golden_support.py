from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
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


class DummyBotSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class DummyBot:
    def __init__(self) -> None:
        self.session = DummyBotSession()


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
