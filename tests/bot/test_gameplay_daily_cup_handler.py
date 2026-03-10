from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.bot.handlers import gameplay_daily_cup
from app.bot.texts.de import TEXTS_DE
from app.game.tournaments.errors import TournamentFullError, TournamentNotFoundError
from tests.bot.helpers import DummyCallback


@pytest.mark.asyncio
async def test_handle_daily_cup_join_shows_german_full_message(monkeypatch) -> None:
    async def _raise_full(*args, **kwargs) -> None:
        raise TournamentFullError

    gameplay_stub = SimpleNamespace(
        SessionLocal=object(),
        UserOnboardingService=object(),
        emit_analytics_event=object(),
        EVENT_SOURCE_BOT="BOT",
    )
    monkeypatch.setattr(gameplay_daily_cup, "_gameplay", lambda: gameplay_stub)
    monkeypatch.setattr(gameplay_daily_cup.daily_cup_flow, "handle_daily_cup_join", _raise_full)

    callback = DummyCallback(
        data=f"daily:cup:join:{uuid4()}",
        from_user=SimpleNamespace(id=123),
    )

    await gameplay_daily_cup.handle_daily_cup_join(callback)

    assert callback.answer_calls == [{"text": TEXTS_DE["msg.daily_cup.full"], "show_alert": True}]


@pytest.mark.asyncio
async def test_handle_daily_cup_view_shows_not_found_for_stale_tournament(monkeypatch) -> None:
    async def _raise_not_found(*args, **kwargs) -> None:
        raise TournamentNotFoundError

    gameplay_stub = SimpleNamespace(
        SessionLocal=object(),
        UserOnboardingService=object(),
        emit_analytics_event=object(),
        EVENT_SOURCE_BOT="BOT",
    )
    monkeypatch.setattr(gameplay_daily_cup, "_gameplay", lambda: gameplay_stub)
    monkeypatch.setattr(
        gameplay_daily_cup.daily_cup_flow, "handle_daily_cup_view", _raise_not_found
    )

    callback = DummyCallback(
        data=f"daily:cup:view:{uuid4()}",
        from_user=SimpleNamespace(id=123),
    )

    await gameplay_daily_cup.handle_daily_cup_view(callback)

    assert callback.answer_calls == [
        {"text": TEXTS_DE["msg.tournament.not_found"], "show_alert": True}
    ]
