from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.workers.tasks import (
    daily_cup_messaging,
    daily_cup_start,
    friend_challenges_utils,
    tournaments_messaging,
    tournaments_proof_cards,
)
from tests.workers.daily_cup_turn_reminder_test_support import session_local_with_sessions


def test_start_daily_arena_round_one_sets_round_fields(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    deadline = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    tournament = SimpleNamespace(
        registration_deadline=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
        current_round=0,
        status="REGISTRATION",
        round_deadline=None,
        round_start_time=None,
    )
    now = datetime(2026, 1, 1, 11, 30, 10, 123, tzinfo=timezone.utc)

    async def _create_round_matches(_session, **kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(daily_cup_start, "get_round_deadline", lambda **_kwargs: deadline)
    monkeypatch.setattr(daily_cup_start, "create_round_matches", _create_round_matches)

    asyncio.run(
        daily_cup_start.start_daily_arena_round_one(
            cast(Any, "session"),
            tournament=cast(Any, tournament),
            participants=cast(Any, ["p1"]),
            now_utc=now,
        )
    )

    assert tournament.current_round == 1
    assert tournament.status == "ROUND_1"
    assert tournament.round_deadline == deadline
    assert tournament.round_start_time == now.replace(microsecond=0)
    assert calls[0]["participants"] == ["p1"]


def test_resolve_telegram_targets_loads_users(monkeypatch) -> None:
    async def _users(_session, user_ids):
        return [SimpleNamespace(id=user_id, telegram_user_id=user_id * 100) for user_id in user_ids]

    monkeypatch.setattr(friend_challenges_utils, "SessionLocal", session_local_with_sessions("s"))
    monkeypatch.setattr(friend_challenges_utils.UsersRepo, "list_by_ids", _users)

    assert asyncio.run(friend_challenges_utils.resolve_telegram_targets(set())) == {}
    result = asyncio.run(friend_challenges_utils.resolve_telegram_targets({2, 1}))
    assert result == {1: 100, 2: 200}


def test_tournaments_proof_card_helpers_and_invalid_paths(monkeypatch) -> None:
    CeleryLike = type("CeleryLike", (), {})
    CeleryLike.__module__ = "celery.local"

    assert tournaments_proof_cards._is_celery_task(CeleryLike())
    assert tournaments_proof_cards._format_user_label(username=" ada ", first_name=None) == "@ada"
    assert tournaments_proof_cards._format_user_label(username=None, first_name=" Bea ") == "Bea"
    assert tournaments_proof_cards._format_user_label(username=" ", first_name=" ") == "Spieler"
    assert tournaments_proof_cards._format_points(Decimal("2.5000")) == "2.5"
    assert tournaments_proof_cards._format_points(Decimal("3.0")) == "3"
    assert tournaments_proof_cards._format_tournament_format("QUICK_12") == "12 Fragen"
    assert "Platz #2" in tournaments_proof_cards._build_caption(place=2, points="5")

    assert asyncio.run(
        tournaments_proof_cards.run_private_tournament_proof_cards_async(tournament_id="bad")
    ) == {
        "processed": 0,
        "participants_total": 0,
        "sent": 0,
        "cached_reused": 0,
        "failed": 0,
    }

    async def _none_context(**_kwargs):
        return None

    monkeypatch.setattr(tournaments_proof_cards, "SessionLocal", session_local_with_sessions("s"))
    monkeypatch.setattr(tournaments_proof_cards, "load_proof_card_context", _none_context)
    assert (
        asyncio.run(
            tournaments_proof_cards.run_private_tournament_proof_cards_async(
                tournament_id=str(uuid4())
            )
        )["processed"]
        == 0
    )


def test_tournaments_messaging_share_helpers_and_enqueue(monkeypatch) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="A", callback_data="a")],
            [InlineKeyboardButton(text="B", callback_data="b")],
        ]
    )
    updated = tournaments_messaging._with_standings_share_button(
        keyboard=keyboard,
        share_url="https://example.test/share",
    )
    assert updated.inline_keyboard[1][0].url == "https://example.test/share"

    monkeypatch.setattr(tournaments_messaging, "public_bot_start_link", lambda **_kwargs: "bot")
    monkeypatch.setattr(
        tournaments_messaging,
        "build_tournament_share_url",
        lambda **kwargs: f"{kwargs['base_link']}:{kwargs['share_text']}",
    )
    assert "Deutsch-Turnier" in tournaments_messaging._build_standings_share_url(
        invite_code="abc",
        tournament_name=None,
    )

    coros: list[object] = []
    warnings: list[dict[str, object]] = []

    def _run(coro) -> None:
        coros.append(coro)
        coro.close()

    monkeypatch.setattr(tournaments_messaging, "_is_celery_task", lambda _task: False)
    monkeypatch.setattr(tournaments_messaging, "run_async_job", _run)
    tournaments_messaging.enqueue_private_tournament_round_messaging(tournament_id="tid")
    assert len(coros) == 1

    def _raise(coro) -> None:
        coro.close()
        raise RuntimeError("queue")

    monkeypatch.setattr(tournaments_messaging, "run_async_job", _raise)
    monkeypatch.setattr(
        tournaments_messaging,
        "logger",
        SimpleNamespace(
            warning=lambda event, **kwargs: warnings.append({"event": event, **kwargs})
        ),
    )
    tournaments_messaging.enqueue_private_tournament_round_messaging(tournament_id="tid")
    assert warnings[0]["event"] == "private_tournament_round_message_enqueue_failed"


def test_daily_cup_messaging_small_wrappers(monkeypatch) -> None:
    assert (
        asyncio.run(daily_cup_messaging.run_daily_cup_round_messaging_async(tournament_id="bad"))[
            "processed"
        ]
        == 0
    )

    calls: list[dict[str, object]] = []
    task = SimpleNamespace(delay=lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(daily_cup_messaging, "run_daily_cup_round_messaging", task)
    monkeypatch.setattr(daily_cup_messaging, "is_celery_task", lambda _task: True)

    daily_cup_messaging.enqueue_daily_cup_round_messaging(
        tournament_id="tid",
        enqueue_completion_followups=True,
    )

    assert calls == [{"tournament_id": "tid", "enqueue_completion_followups": True}]
