from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from app.workers.tasks import daily_cup_match_results


class _DummyBotSession:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _RecordingBot:
    def __init__(self, *, forbidden_chat_id: int | None = None) -> None:
        self.session = _DummyBotSession()
        self.forbidden_chat_id = forbidden_chat_id
        self.messages: list[dict[str, Any]] = []

    async def send_message(self, **kwargs) -> None:
        chat_id = int(kwargs["chat_id"])
        if self.forbidden_chat_id is not None and chat_id == self.forbidden_chat_id:
            raise TelegramForbiddenError(
                method=SendMessage(chat_id=chat_id, text="x"),
                message="forbidden",
            )
        self.messages.append(kwargs)


@pytest.mark.asyncio
async def test_send_match_result_messages_sends_for_both_participants(monkeypatch) -> None:
    participants = [
        SimpleNamespace(user_id=11, score=Decimal("2.5")),
        SimpleNamespace(user_id=22, score=Decimal("2.0")),
        SimpleNamespace(user_id=33, score=Decimal("1.0")),
    ]
    users = [
        SimpleNamespace(id=11, telegram_user_id=1011),
        SimpleNamespace(id=22, telegram_user_id=1022),
    ]
    bot = _RecordingBot()

    async def _fake_list_for_tournament(*args, **kwargs):
        return participants

    async def _fake_list_by_ids(*args, **kwargs):
        return users

    monkeypatch.setattr(
        daily_cup_match_results.TournamentParticipantsRepo,
        "list_for_tournament",
        _fake_list_for_tournament,
    )
    monkeypatch.setattr(daily_cup_match_results.UsersRepo, "list_by_ids", _fake_list_by_ids)
    monkeypatch.setattr(daily_cup_match_results, "build_bot", lambda: bot)

    tournament_id = uuid4()
    await daily_cup_match_results.send_daily_cup_match_result_messages(
        session=SimpleNamespace(),  # type: ignore[arg-type]
        tournament_id=tournament_id,
        round_no=2,
        user_a=11,
        user_b=22,
        user_a_points=4,
        user_b_points=3,
        rounds_total=3,
        tournament_registration_deadline=datetime(2026, 3, 3, 17, 0, tzinfo=UTC),
        next_round_start_time=datetime(2026, 3, 3, 18, 0, tzinfo=UTC),
    )

    assert bot.session.closed is True
    assert len(bot.messages) == 2
    by_chat = {int(item["chat_id"]): str(item["text"]) for item in bot.messages}
    assert 1011 in by_chat
    assert 1022 in by_chat
    assert "Runde 3 startet um 19:00 (Berlin)" in by_chat[1011]
    assert "Runde 3 startet um 19:00 (Berlin)" in by_chat[1022]


@pytest.mark.asyncio
async def test_send_match_result_messages_uses_planned_slot_when_next_round_not_started(
    monkeypatch,
) -> None:
    participants = [
        SimpleNamespace(user_id=11, score=Decimal("2.5")),
        SimpleNamespace(user_id=22, score=Decimal("2.0")),
    ]
    users = [
        SimpleNamespace(id=11, telegram_user_id=1011),
        SimpleNamespace(id=22, telegram_user_id=1022),
    ]
    bot = _RecordingBot()

    async def _fake_list_for_tournament(*args, **kwargs):
        return participants

    async def _fake_list_by_ids(*args, **kwargs):
        return users

    monkeypatch.setattr(
        daily_cup_match_results.TournamentParticipantsRepo,
        "list_for_tournament",
        _fake_list_for_tournament,
    )
    monkeypatch.setattr(daily_cup_match_results.UsersRepo, "list_by_ids", _fake_list_by_ids)
    monkeypatch.setattr(daily_cup_match_results, "build_bot", lambda: bot)

    await daily_cup_match_results.send_daily_cup_match_result_messages(
        session=SimpleNamespace(),  # type: ignore[arg-type]
        tournament_id=uuid4(),
        round_no=3,
        user_a=11,
        user_b=22,
        user_a_points=4,
        user_b_points=3,
        rounds_total=4,
        tournament_registration_deadline=datetime(2026, 3, 3, 17, 0, tzinfo=UTC),
        next_round_start_time=None,
    )

    by_chat = {int(item["chat_id"]): str(item["text"]) for item in bot.messages}
    assert "Runde 4 startet voraussichtlich 19:30 (Berlin)" in by_chat[1011]
    assert "Runde 4 startet voraussichtlich 19:30 (Berlin)" in by_chat[1022]


@pytest.mark.asyncio
async def test_send_match_result_messages_ignores_forbidden_and_continues(monkeypatch) -> None:
    participants = [
        SimpleNamespace(user_id=11, score=Decimal("3")),
        SimpleNamespace(user_id=22, score=Decimal("2")),
    ]
    users = [
        SimpleNamespace(id=11, telegram_user_id=1011),
        SimpleNamespace(id=22, telegram_user_id=1022),
    ]
    bot = _RecordingBot(forbidden_chat_id=1011)

    async def _fake_list_for_tournament(*args, **kwargs):
        return participants

    async def _fake_list_by_ids(*args, **kwargs):
        return users

    monkeypatch.setattr(
        daily_cup_match_results.TournamentParticipantsRepo,
        "list_for_tournament",
        _fake_list_for_tournament,
    )
    monkeypatch.setattr(daily_cup_match_results.UsersRepo, "list_by_ids", _fake_list_by_ids)
    monkeypatch.setattr(daily_cup_match_results, "build_bot", lambda: bot)

    await daily_cup_match_results.send_daily_cup_match_result_messages(
        session=SimpleNamespace(),  # type: ignore[arg-type]
        tournament_id=uuid4(),
        round_no=3,
        user_a=11,
        user_b=22,
        user_a_points=2,
        user_b_points=2,
        rounds_total=3,
        tournament_registration_deadline=None,
        next_round_start_time=None,
    )

    assert bot.session.closed is True
    assert len(bot.messages) == 1
    assert int(bot.messages[0]["chat_id"]) == 1022
    assert "Finale Auswertung" in str(bot.messages[0]["text"])
