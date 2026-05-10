from __future__ import annotations

from uuid import uuid4

import pytest

from app.game.tournaments import service, service_facade, start
from tests.game.tournaments_unit_support import NOW_UTC, TournamentSession


@pytest.mark.asyncio
async def test_service_facade_delegates_public_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def _record(name: str):
        async def _inner(*_args, **_kwargs):
            calls.append(name)
            return name

        return _inner

    monkeypatch.setattr(service_facade, "create_private_tournament", await _record("create"))
    monkeypatch.setattr(service_facade, "join_private_tournament_by_code", await _record("join"))
    monkeypatch.setattr(service_facade, "join_daily_cup_by_id", await _record("daily_join"))
    monkeypatch.setattr(
        service_facade, "get_private_tournament_lobby_by_id", await _record("get_id")
    )
    monkeypatch.setattr(
        service_facade,
        "get_private_tournament_lobby_by_invite_code",
        await _record("get_code"),
    )
    monkeypatch.setattr(service_facade, "get_daily_cup_lobby_by_id", await _record("daily_get"))
    monkeypatch.setattr(service_facade, "start_private_tournament", await _record("start"))
    facade = service_facade.TournamentServiceFacade

    assert (
        await facade.create_private_tournament(
            TournamentSession(), created_by=1, format_code="QUICK_5", now_utc=NOW_UTC
        )
        == "create"
    )
    assert (
        await facade.join_private_tournament_by_code(
            TournamentSession(), user_id=1, invite_code="abc", now_utc=NOW_UTC
        )
        == "join"
    )
    assert (
        await facade.join_daily_cup_by_id(
            TournamentSession(), user_id=1, tournament_id=uuid4(), now_utc=NOW_UTC
        )
        == "daily_join"
    )
    assert (
        await facade.get_private_tournament_lobby_by_id(
            TournamentSession(), tournament_id=uuid4(), viewer_user_id=1
        )
        == "get_id"
    )
    assert (
        await facade.get_private_tournament_lobby_by_invite_code(
            TournamentSession(), invite_code="abc", viewer_user_id=1
        )
        == "get_code"
    )
    assert (
        await facade.get_daily_cup_lobby_by_id(
            TournamentSession(), tournament_id=uuid4(), viewer_user_id=1
        )
        == "daily_get"
    )
    assert (
        await facade.start_private_tournament(
            TournamentSession(), creator_user_id=1, tournament_id=uuid4(), now_utc=NOW_UTC
        )
        == "start"
    )
    assert calls == ["create", "join", "daily_join", "get_id", "get_code", "daily_get", "start"]


def test_service_module_exports_public_api() -> None:
    assert "start_private_tournament" in service.__all__
    assert service.start_private_tournament is start.start_private_tournament
