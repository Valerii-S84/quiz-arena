from __future__ import annotations

from uuid import UUID

import pytest

from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.session import SessionLocal
from app.workers.tasks import daily_cup_proof_cards
from tests.integration.daily_cup_proof_cards_test_support import (
    create_completed_daily_cup,
    create_daily_cup_users,
    ensure_tournament_schema,
    fixed_daily_cup_now,
    install_recording_worker_bot,
)


@pytest.mark.asyncio
async def test_daily_cup_proof_cards_send_only_once_per_participant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = fixed_daily_cup_now()
    await ensure_tournament_schema()

    user_ids = await create_daily_cup_users(prefix="daily_cup_proof", count=4)
    tournament_id = await create_completed_daily_cup(now_utc=now_utc, user_ids=user_ids)
    bot, render_calls = install_recording_worker_bot(monkeypatch, record_renders=True)

    first = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )
    assert int(first["sent"]) == 4
    assert int(first["cached_reused"]) == 0
    assert int(first["failed"]) == 0
    assert all(not isinstance(item["photo"], str) for item in bot.send_photos)
    assert [str(item.get("caption")) for item in bot.send_photos[:4]] == [
        "🏆 Daily Arena Cup\nPlatz #1\nPunkte: 4\n📱 https://t.me/Deine_Deutsch_Quiz_bot",
        "🏆 Daily Arena Cup\nPlatz #2\nPunkte: 3\n📱 https://t.me/Deine_Deutsch_Quiz_bot",
        "🏆 Daily Arena Cup\nPlatz #3\nPunkte: 2\n📱 https://t.me/Deine_Deutsch_Quiz_bot",
        "🏆 Daily Arena Cup\nPlatz #4\nPunkte: 1\n📱 https://t.me/Deine_Deutsch_Quiz_bot",
    ]
    first_batch_buttons = [
        button.switch_inline_query
        for item in bot.send_photos[:4]
        for row in item["reply_markup"].inline_keyboard
        for button in row
        if button.switch_inline_query
    ]
    assert len(first_batch_buttons) == 4
    assert all(query and query.startswith("proof:daily:") for query in first_batch_buttons)
    assert len(render_calls) == 4
    assert all(call["rounds_played"] == 3 for call in render_calls)

    first_batch = len(bot.send_photos)
    parsed_tournament_id = UUID(tournament_id)
    async with SessionLocal.begin() as session:
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=parsed_tournament_id,
        )
    assert all(item.proof_card_sent is True for item in participants)

    second = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )
    assert int(second["sent"]) == 0
    assert int(second["cached_reused"]) == 0
    assert int(second["failed"]) == 0
    second_batch = bot.send_photos[first_batch:]
    assert second_batch == []


@pytest.mark.asyncio
async def test_daily_cup_proof_cards_skip_repeat_enqueue_for_same_participant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = fixed_daily_cup_now()
    await ensure_tournament_schema()

    user_ids = await create_daily_cup_users(prefix="daily_cup_proof_single", count=4)
    tournament_id = await create_completed_daily_cup(now_utc=now_utc, user_ids=user_ids)

    bot, _render_calls = install_recording_worker_bot(monkeypatch)

    first = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        user_id=user_ids[0],
        initial_delay_seconds=0,
    )
    assert first == {
        "processed": 1,
        "participants_total": 4,
        "sent": 1,
        "cached_reused": 0,
        "failed": 0,
    }

    second = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        user_id=user_ids[0],
        initial_delay_seconds=0,
    )
    assert second == {
        "processed": 1,
        "participants_total": 4,
        "sent": 0,
        "cached_reused": 0,
        "failed": 0,
    }
    assert len(bot.send_photos) == 1
