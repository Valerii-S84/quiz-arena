from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.workers.tasks import daily_cup_proof_cards
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


@pytest.mark.asyncio
async def test_daily_cup_proof_cards_reuse_cached_file_ids_on_second_run(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
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
