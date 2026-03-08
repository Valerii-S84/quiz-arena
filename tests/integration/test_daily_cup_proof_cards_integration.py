from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournament_round_scores_repo import (
    TournamentRoundScorePayload,
    TournamentRoundScoresRepo,
)
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.daily_cup_standings import calculate_daily_cup_standings
from app.workers.tasks import daily_cup_proof_cards
from app.workers.tasks.daily_cup_config import DAILY_CUP_TIMEZONE
from tests.integration.friend_challenge_fixtures import _create_user
from tests.integration.test_private_tournament_worker_integration import (
    _DummyWorkerBot,
    _ensure_tournament_schema,
)

UTC = timezone.utc


async def _create_completed_daily_cup(*, now_utc: datetime, user_ids: list[int]) -> str:
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.create(
            session,
            tournament=Tournament(
                id=uuid4(),
                type="DAILY_ARENA",
                created_by=None,
                name="Daily Arena Cup",
                status="COMPLETED",
                format="QUICK_5",
                max_participants=8,
                current_round=3,
                registration_deadline=now_utc - timedelta(hours=5),
                round_deadline=None,
                invite_code=uuid4().hex[:12],
                created_at=now_utc - timedelta(hours=6),
            ),
        )
        for user_id in user_ids:
            await TournamentParticipantsRepo.create_once(
                session,
                tournament_id=tournament.id,
                user_id=user_id,
                joined_at=now_utc - timedelta(hours=4),
            )
        participants = await TournamentParticipantsRepo.list_for_tournament_for_update(
            session,
            tournament_id=tournament.id,
        )
        assert len(participants) == len(user_ids)
        score_values = [Decimal("4"), Decimal("3"), Decimal("2"), Decimal("1")]
        for index, row in enumerate(participants):
            row.score = score_values[index]
            row.tie_break = Decimal(index)
        return str(tournament.id)


async def _create_completed_daily_cup_with_seeded_scores(
    *,
    now_utc: datetime,
    user_ids: list[int],
) -> str:
    round_specs: dict[int, tuple[tuple[int, int, int], ...]] = {
        user_ids[0]: ((2, 7, 700), (2, 6, 650), (2, 6, 600), (2, 5, 550)),
        user_ids[1]: ((2, 6, 750), (2, 6, 700), (2, 5, 650), (1, 5, 600)),
        user_ids[2]: ((2, 6, 800), (1, 5, 750), (2, 5, 700), (1, 4, 650)),
        user_ids[3]: ((2, 5, 850), (1, 5, 800), (1, 4, 750), (1, 4, 700)),
        user_ids[4]: ((2, 5, 900), (1, 4, 850), (1, 4, 800), (0, 4, 750)),
        user_ids[5]: ((1, 4, 950), (1, 4, 900), (1, 4, 850), (0, 3, 800)),
        user_ids[6]: ((1, 4, 1000), (1, 3, 950), (0, 3, 900), (0, 3, 850)),
        user_ids[7]: ((1, 3, 1050), (0, 3, 1000), (0, 3, 950), (0, 2, 900)),
        user_ids[8]: ((0, 2, 1100), (0, 2, 1050), (0, 2, 1000), (0, 2, 950)),
    }

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.create(
            session,
            tournament=Tournament(
                id=uuid4(),
                type="DAILY_ARENA",
                created_by=None,
                name="Daily Arena Cup",
                status="COMPLETED",
                format="QUICK_5",
                max_participants=100,
                current_round=4,
                registration_deadline=now_utc - timedelta(hours=5),
                round_deadline=None,
                invite_code=uuid4().hex[:12],
                created_at=now_utc - timedelta(hours=6),
            ),
        )
        for index, user_id in enumerate(user_ids):
            await TournamentParticipantsRepo.create_once(
                session,
                tournament_id=tournament.id,
                user_id=user_id,
                joined_at=now_utc - timedelta(hours=4) + timedelta(minutes=index),
            )

        for user_id, rounds in round_specs.items():
            total_points = Decimal("0")
            total_correct = Decimal("0")
            for round_number, (points, correct_answers, total_time_ms) in enumerate(rounds, start=1):
                total_points += Decimal(points)
                total_correct += Decimal(correct_answers)
                await TournamentRoundScoresRepo.upsert_result(
                    session,
                    payload=TournamentRoundScorePayload(
                        tournament_id=tournament.id,
                        round_number=round_number,
                        player_id=user_id,
                        opponent_id=None,
                        wins=points,
                        is_draw=points == 1,
                        correct_answers=correct_answers,
                        total_time_ms=total_time_ms,
                        got_bye=False,
                        auto_finished=False,
                        created_at=now_utc,
                    ),
                )
            participant = await TournamentParticipantsRepo.get_for_tournament_user(
                session,
                tournament_id=tournament.id,
                user_id=user_id,
            )
            assert participant is not None
            participant.score = total_points
            participant.tie_break = total_correct

        return str(tournament.id)


@pytest.mark.asyncio
async def test_daily_cup_proof_cards_reuse_cached_file_ids_on_second_run(monkeypatch) -> None:
    # Keep registration and runtime on the same local day for DAILY_CUP_TIMEZONE.
    now_utc = (
        datetime.now(UTC)
        .astimezone(ZoneInfo(DAILY_CUP_TIMEZONE))
        .replace(hour=12, minute=0, second=0, microsecond=0)
        .astimezone(UTC)
    )
    await _ensure_tournament_schema()

    user_ids = [await _create_user(f"daily_cup_proof_{idx}") for idx in range(4)]
    tournament_id = await _create_completed_daily_cup(now_utc=now_utc, user_ids=user_ids)

    bot = _DummyWorkerBot()
    monkeypatch.setattr(daily_cup_proof_cards, "build_bot", lambda: bot)

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

    first_batch = len(bot.send_photos)
    second = await daily_cup_proof_cards.run_daily_cup_proof_cards_async(
        tournament_id=tournament_id,
        initial_delay_seconds=0,
    )
    assert int(second["sent"]) == 4
    assert int(second["cached_reused"]) == 4
    assert int(second["failed"]) == 0
    second_batch = bot.send_photos[first_batch:]
    assert len(second_batch) == 4
    assert all(isinstance(item["photo"], str) for item in second_batch)


@pytest.mark.asyncio
async def test_daily_cup_proof_cards_send_nine_cards_with_expected_places_and_points(
    monkeypatch,
) -> None:
    now_utc = (
        datetime.now(UTC)
        .astimezone(ZoneInfo(DAILY_CUP_TIMEZONE))
        .replace(hour=12, minute=0, second=0, microsecond=0)
        .astimezone(UTC)
    )
    await _ensure_tournament_schema()

    user_ids = [await _create_user(f"daily_cup_proof_nine_{idx}") for idx in range(9)]
    tournament_id = await _create_completed_daily_cup_with_seeded_scores(
        now_utc=now_utc,
        user_ids=user_ids,
    )
    render_calls: list[dict[str, object]] = []

    def _fake_render(**kwargs) -> bytes:
        render_calls.append(kwargs)
        return b"png"

    bot = _DummyWorkerBot()
    monkeypatch.setattr(daily_cup_proof_cards, "build_bot", lambda: bot)
    monkeypatch.setattr(daily_cup_proof_cards, "render_tournament_proof_card_png", _fake_render)

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
