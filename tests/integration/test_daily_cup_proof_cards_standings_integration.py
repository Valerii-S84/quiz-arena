from __future__ import annotations

from uuid import UUID

import pytest

from app.db.session import SessionLocal
from app.game.tournaments.daily_cup_standings import calculate_daily_cup_standings
from app.workers.tasks import daily_cup_proof_cards
from tests.integration.daily_cup_proof_cards_test_support import (
    create_completed_daily_cup_with_seeded_scores,
    create_daily_cup_users,
    ensure_tournament_schema,
    fixed_daily_cup_now,
    install_recording_worker_bot,
)


@pytest.mark.asyncio
async def test_daily_cup_proof_cards_send_nine_cards_with_expected_places_and_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = fixed_daily_cup_now()
    await ensure_tournament_schema()

    user_ids = await create_daily_cup_users(prefix="daily_cup_proof_nine", count=9)
    tournament_id = await create_completed_daily_cup_with_seeded_scores(
        now_utc=now_utc,
        user_ids=user_ids,
    )
    bot, render_calls = install_recording_worker_bot(monkeypatch, record_renders=True)

    parsed_tournament_id = UUID(tournament_id)
    async with SessionLocal.begin() as session:
        standings = await calculate_daily_cup_standings(session, tournament_id=parsed_tournament_id)

    assert len(standings) == 9
    assert [(item.place, item.wins, item.correct_answers) for item in standings] == [
        (1, 8, 24),
        (2, 7, 22),
        (3, 6, 20),
        (4, 5, 18),
        (5, 4, 17),
        (6, 3, 15),
        (7, 2, 13),
        (8, 1, 11),
        (9, 0, 8),
    ]

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )

    assert result == {
        "processed": 1,
        "participants_total": 9,
        "sent": 9,
        "cached_reused": 0,
        "failed": 0,
    }
    assert len(bot.send_photos) == 9
    assert len(render_calls) == 9
    assert [call["place"] for call in render_calls] == list(range(1, 10))
    assert all(call["format_label"] == "7 Fragen" for call in render_calls)
    assert all(call["rounds_played"] == 4 for call in render_calls)

    expected_points = [str(int(item.participant.score)) for item in standings]
    expected_captions = [
        f"🏆 Daily Arena Cup\nPlatz #{item.place}\nPunkte: {points}\n📱 https://t.me/Deine_Deutsch_Quiz_bot"
        for item, points in zip(standings, expected_points, strict=False)
    ]
    assert [str(item.get("caption")) for item in bot.send_photos] == expected_captions


@pytest.mark.asyncio
async def test_daily_cup_proof_cards_use_four_rounds_for_twenty_one_players(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_utc = fixed_daily_cup_now()
    await ensure_tournament_schema()

    user_ids = await create_daily_cup_users(prefix="daily_cup_proof_large", count=21)
    tournament_id = await create_completed_daily_cup_with_seeded_scores(
        now_utc=now_utc,
        user_ids=user_ids,
    )
    _bot, render_calls = install_recording_worker_bot(monkeypatch, record_renders=True)

    result = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )

    assert result == {
        "processed": 1,
        "participants_total": 21,
        "sent": 21,
        "cached_reused": 0,
        "failed": 0,
    }
    assert len(render_calls) == 21
    assert all(call["rounds_played"] == 4 for call in render_calls)
