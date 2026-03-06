from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.bot.handlers.gameplay_flows.daily_cup_views import render_daily_cup_lobby
from tests.bot.helpers import DummyCallback, DummyMessage


@pytest.mark.asyncio
async def test_render_daily_cup_lobby_registration_shows_registered_waiting_hint() -> None:
    callback = DummyCallback(
        data="daily:cup:view:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )
    lobby = SimpleNamespace(
        tournament=SimpleNamespace(
            tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            status="REGISTRATION",
            current_round=0,
            round_deadline=None,
        ),
        participants=(
            SimpleNamespace(user_id=101, score=Decimal("0"), tie_break=Decimal("0")),
            SimpleNamespace(user_id=202, score=Decimal("0"), tie_break=Decimal("0")),
        ),
        viewer_joined=True,
        viewer_current_match_challenge_id=None,
        viewer_current_opponent_user_id=None,
    )

    await render_daily_cup_lobby(
        callback,
        lobby=lobby,
        user_id=101,
        labels={101: "Ich", 202: "Max"},
    )

    response = callback.message.answers[0]
    text = response.text or ""
    assert "Du bist im heutigen Cup registriert." in text
    assert "Start um 18:00." in text


@pytest.mark.asyncio
async def test_render_daily_cup_lobby_registration_shows_rules_for_not_joined_user() -> None:
    callback = DummyCallback(
        data="daily:cup:view:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=303),
        message=DummyMessage(),
    )
    lobby = SimpleNamespace(
        tournament=SimpleNamespace(
            tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            status="REGISTRATION",
            current_round=0,
            round_deadline=None,
        ),
        participants=(
            SimpleNamespace(user_id=101, score=Decimal("0"), tie_break=Decimal("0")),
            SimpleNamespace(user_id=202, score=Decimal("0"), tie_break=Decimal("0")),
        ),
        viewer_joined=False,
        viewer_current_match_challenge_id=None,
        viewer_current_opponent_user_id=None,
    )

    await render_daily_cup_lobby(
        callback,
        lobby=lobby,
        user_id=303,
        labels={101: "Ich", 202: "Max"},
    )

    response = callback.message.answers[0]
    text = response.text or ""
    assert "Heute im Cup" in text
    assert "Kein Ausscheiden" in text
    assert "Du?" in text


@pytest.mark.asyncio
async def test_render_daily_cup_lobby_round_active_shows_active_hint() -> None:
    callback = DummyCallback(
        data="daily:cup:view:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )
    lobby = SimpleNamespace(
        tournament=SimpleNamespace(
            tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            status="ROUND_2",
            current_round=2,
            round_deadline=None,
        ),
        participants=(
            SimpleNamespace(user_id=101, score=Decimal("1"), tie_break=Decimal("0")),
            SimpleNamespace(user_id=202, score=Decimal("1"), tie_break=Decimal("0")),
        ),
        viewer_joined=True,
        viewer_current_match_challenge_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        viewer_current_opponent_user_id=202,
    )

    await render_daily_cup_lobby(
        callback,
        lobby=lobby,
        user_id=101,
        labels={101: "Ich", 202: "Max"},
    )

    response = callback.message.answers[0]
    text = response.text or ""
    assert "Dein Duell ist bereit." in text
    assert "Gegner: Max" in text
    buttons = [button for row in response.kwargs["reply_markup"].inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "friend:next:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" in callbacks


@pytest.mark.asyncio
async def test_render_daily_cup_lobby_round_active_shows_arena_bot_for_self_match() -> None:
    callback = DummyCallback(
        data="daily:cup:view:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )
    lobby = SimpleNamespace(
        tournament=SimpleNamespace(
            tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            status="ROUND_1",
            current_round=1,
            round_deadline=None,
        ),
        participants=(
            SimpleNamespace(user_id=101, score=Decimal("0"), tie_break=Decimal("0")),
            SimpleNamespace(user_id=202, score=Decimal("0"), tie_break=Decimal("0")),
        ),
        viewer_joined=True,
        viewer_current_match_challenge_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        viewer_current_opponent_user_id=None,
    )

    await render_daily_cup_lobby(
        callback,
        lobby=lobby,
        user_id=101,
        labels={101: "Ich", 202: "Max"},
    )

    response = callback.message.answers[0]
    text = response.text or ""
    assert "Dein Duell ist bereit." in text
    assert "Gegner: Arena Bot" in text


@pytest.mark.asyncio
async def test_render_daily_cup_lobby_round_waiting_shows_next_round_time() -> None:
    callback = DummyCallback(
        data="daily:cup:view:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )
    lobby = SimpleNamespace(
        tournament=SimpleNamespace(
            tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            status="ROUND_1",
            current_round=1,
            round_deadline=datetime(2026, 3, 3, 19, 0, tzinfo=UTC),
        ),
        participants=(
            SimpleNamespace(user_id=101, score=Decimal("1"), tie_break=Decimal("0")),
            SimpleNamespace(user_id=202, score=Decimal("0"), tie_break=Decimal("0")),
        ),
        viewer_joined=True,
        viewer_current_match_challenge_id=None,
        viewer_current_opponent_user_id=None,
    )

    await render_daily_cup_lobby(
        callback,
        lobby=lobby,
        user_id=101,
        labels={101: "Ich", 202: "Max"},
    )

    response = callback.message.answers[0]
    text = response.text or ""
    assert "Nächste Runde startet um 20:00 (Berlin)." in text


@pytest.mark.asyncio
async def test_render_daily_cup_lobby_round_waiting_final_round_shows_completion_wait_hint() -> (
    None
):
    callback = DummyCallback(
        data="daily:cup:view:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )
    lobby = SimpleNamespace(
        tournament=SimpleNamespace(
            tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            status="ROUND_3",
            current_round=3,
            round_deadline=None,
        ),
        participants=(
            SimpleNamespace(user_id=101, score=Decimal("2"), tie_break=Decimal("0")),
            SimpleNamespace(user_id=202, score=Decimal("2"), tie_break=Decimal("0")),
        ),
        viewer_joined=True,
        viewer_current_match_challenge_id=None,
        viewer_current_opponent_user_id=None,
    )

    await render_daily_cup_lobby(
        callback,
        lobby=lobby,
        user_id=101,
        labels={101: "Ich", 202: "Max"},
    )

    response = callback.message.answers[0]
    text = response.text or ""
    assert "Warte auf den Abschluss des Cups." in text


@pytest.mark.asyncio
async def test_render_daily_cup_lobby_completed_shows_completed_marker() -> None:
    callback = DummyCallback(
        data="daily:cup:view:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        from_user=SimpleNamespace(id=101),
        message=DummyMessage(),
    )
    lobby = SimpleNamespace(
        tournament=SimpleNamespace(
            tournament_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            status="COMPLETED",
            current_round=3,
            round_deadline=None,
        ),
        participants=(
            SimpleNamespace(user_id=101, score=Decimal("3.0"), tie_break=Decimal("9.0")),
            SimpleNamespace(user_id=202, score=Decimal("2.0"), tie_break=Decimal("4.5")),
        ),
        viewer_joined=True,
        viewer_current_match_challenge_id=None,
        viewer_current_opponent_user_id=None,
    )

    await render_daily_cup_lobby(
        callback,
        lobby=lobby,
        user_id=101,
        labels={101: "Ich", 202: "Max"},
    )

    response = callback.message.answers[0]
    text = response.text or ""
    assert "Daily Arena Cup — Abgeschlossen!" in text
    assert "Dein Ergebnis: Platz 1" in text
    assert "Deadline: -" not in text
    assert "TB 9" in text
    assert "TB 4.5" in text
    buttons = [button for row in response.kwargs["reply_markup"].inline_keyboard for button in row]
    callbacks = [button.callback_data for button in buttons if button.callback_data]
    assert "daily:cup:share:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" in callbacks
