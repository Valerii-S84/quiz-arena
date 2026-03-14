from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers import gameplay_tournaments_more
from app.bot.handlers.gameplay_flows import tournament_flow, tournament_lobby_flow
from app.bot.texts.de import TEXTS_DE
from app.game.tournaments.errors import (
    TournamentAccessError,
    TournamentAlreadyStartedError,
    TournamentClosedError,
    TournamentFullError,
    TournamentInsufficientParticipantsError,
    TournamentNotFoundError,
)
from tests.bot.helpers import DummyCallback, DummyMessage


def _patch_gameplay(monkeypatch) -> SimpleNamespace:
    gameplay = SimpleNamespace(
        SessionLocal=object(),
        UserOnboardingService=object(),
        emit_analytics_event=object(),
        EVENT_SOURCE_BOT="BOT",
    )
    monkeypatch.setattr(gameplay_tournaments_more, "_gameplay", lambda: gameplay)
    return gameplay


@pytest.mark.asyncio
async def test_handle_tournament_copy_link_rejects_missing_data() -> None:
    callback = DummyCallback(data=None, from_user=SimpleNamespace(id=7), message=DummyMessage())

    await gameplay_tournaments_more.handle_tournament_copy_link(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_tournament_copy_link_rejects_invalid_uuid() -> None:
    callback = DummyCallback(
        data="friend:tournament:copy:not-a-uuid",
        from_user=SimpleNamespace(id=7),
        message=DummyMessage(),
    )

    await gameplay_tournaments_more.handle_tournament_copy_link(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.system.error"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_tournament_copy_link_passes_expected_dependencies(monkeypatch) -> None:
    gameplay = _patch_gameplay(monkeypatch)
    captured: dict[str, object] = {}
    tournament_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    async def _fake_handle(callback, **kwargs) -> None:
        captured["callback"] = callback
        captured.update(kwargs)

    monkeypatch.setattr(tournament_lobby_flow, "handle_tournament_copy_link", _fake_handle)

    callback = DummyCallback(
        data=f"friend:tournament:copy:{tournament_id}",
        from_user=SimpleNamespace(id=7),
        message=DummyMessage(),
    )
    await gameplay_tournaments_more.handle_tournament_copy_link(callback)

    assert captured["callback"] is callback
    assert captured["tournament_id"] == tournament_id
    assert captured["session_local"] is gameplay.SessionLocal
    assert captured["user_onboarding_service"] is gameplay.UserOnboardingService
    assert captured["tournament_service"] is gameplay_tournaments_more.TournamentServiceFacade
    assert (
        captured["build_tournament_invite_link"]
        is gameplay_tournaments_more.gameplay_helpers._build_tournament_invite_link
    )


@pytest.mark.asyncio
async def test_handle_tournament_view_passes_expected_dependencies(monkeypatch) -> None:
    gameplay = _patch_gameplay(monkeypatch)
    captured: dict[str, object] = {}
    tournament_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    async def _fake_handle(callback, **kwargs) -> None:
        captured["callback"] = callback
        captured.update(kwargs)

    monkeypatch.setattr(tournament_lobby_flow, "handle_tournament_view", _fake_handle)

    callback = DummyCallback(
        data=f"friend:tournament:view:{tournament_id}",
        from_user=SimpleNamespace(id=7),
        message=DummyMessage(),
    )
    await gameplay_tournaments_more.handle_tournament_view(callback)

    assert captured["callback"] is callback
    assert captured["tournament_id"] == tournament_id
    assert captured["session_local"] is gameplay.SessionLocal
    assert captured["user_onboarding_service"] is gameplay.UserOnboardingService
    assert captured["tournament_service"] is gameplay_tournaments_more.TournamentServiceFacade
    assert captured["users_repo"] is gameplay_tournaments_more.UsersRepo


@pytest.mark.asyncio
async def test_handle_tournament_share_passes_expected_dependencies(monkeypatch) -> None:
    gameplay = _patch_gameplay(monkeypatch)
    captured: dict[str, object] = {}
    tournament_id = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    async def _fake_handle(callback, **kwargs) -> None:
        captured["callback"] = callback
        captured.update(kwargs)

    monkeypatch.setattr(tournament_flow, "handle_tournament_share_result", _fake_handle)

    callback = DummyCallback(
        data=f"friend:tournament:share:{tournament_id}",
        from_user=SimpleNamespace(id=7),
        message=DummyMessage(),
    )
    await gameplay_tournaments_more.handle_tournament_share(callback)

    assert captured["callback"] is callback
    assert captured["tournament_id"] == tournament_id
    assert captured["session_local"] is gameplay.SessionLocal
    assert captured["user_onboarding_service"] is gameplay.UserOnboardingService
    assert captured["tournament_service"] is gameplay_tournaments_more.TournamentServiceFacade
    assert (
        captured["build_tournament_share_result_url"]
        is gameplay_tournaments_more._build_tournament_share_result_url
    )
    assert captured["emit_analytics_event"] is gameplay.emit_analytics_event
    assert captured["event_source_bot"] == "BOT"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exc", "expected_key"),
    [
        (TournamentNotFoundError(), "msg.tournament.not_found"),
        (TournamentAccessError(), "msg.tournament.not_found"),
        (TournamentFullError(), "msg.tournament.full"),
        (TournamentInsufficientParticipantsError(), "msg.tournament.start.need_two"),
        (TournamentClosedError(), "msg.tournament.closed"),
        (TournamentAlreadyStartedError(), "msg.tournament.closed"),
        (RuntimeError("boom"), "msg.system.error"),
    ],
)
async def test_handle_tournament_copy_link_maps_exceptions_to_user_facing_alerts(
    monkeypatch,
    exc: Exception,
    expected_key: str,
) -> None:
    _patch_gameplay(monkeypatch)

    async def _fake_handle(callback, **kwargs) -> None:
        del callback, kwargs
        raise exc

    monkeypatch.setattr(tournament_lobby_flow, "handle_tournament_copy_link", _fake_handle)

    callback = DummyCallback(
        data="friend:tournament:copy:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=7),
        message=DummyMessage(),
    )
    await gameplay_tournaments_more.handle_tournament_copy_link(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE[expected_key], "show_alert": True}]
