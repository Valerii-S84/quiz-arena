from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.service import create_private_tournament, join_private_tournament_by_code
from app.workers.tasks import tournaments_proof_cards
from tests.integration.friend_challenge_fixtures import _create_user
from tests.integration.test_private_tournament_worker_integration import (
    _DummyWorkerBot,
    _ensure_tournament_schema,
)

UTC = timezone.utc


@pytest.mark.asyncio
async def test_proof_cards_use_cached_file_id_on_second_run(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
    await _ensure_tournament_schema()

    creator_user_id = await _create_user("private_tournament_proof_creator")
    user_2 = await _create_user("private_tournament_proof_user_2")
    user_3 = await _create_user("private_tournament_proof_user_3")

    async with SessionLocal.begin() as session:
        tournament = await create_private_tournament(
            session,
            created_by=creator_user_id,
            format_code="QUICK_12",
            now_utc=now_utc,
        )
        await join_private_tournament_by_code(
            session,
            user_id=user_2,
            invite_code=tournament.invite_code,
            now_utc=now_utc,
        )
        await join_private_tournament_by_code(
            session,
            user_id=user_3,
            invite_code=tournament.invite_code,
            now_utc=now_utc,
        )
        participants = await TournamentParticipantsRepo.list_for_tournament_for_update(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert len(participants) == 3
        participants[0].score = 3
        participants[1].score = 2
        participants[2].score = 1

        tournament_row = await TournamentsRepo.get_by_id_for_update(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert tournament_row is not None
        tournament_row.status = "COMPLETED"
        tournament_row.current_round = 3
        tournament_id = str(tournament.tournament_id)

    bot = _DummyWorkerBot()
    monkeypatch.setattr(tournaments_proof_cards, "build_bot", lambda: bot)

    first = await tournaments_proof_cards.run_private_tournament_proof_cards_async(
        tournament_id=tournament_id
    )
    assert int(first["sent"]) == 3
    assert int(first["cached_reused"]) == 0
    assert all(not isinstance(item["photo"], str) for item in bot.send_photos)
    assert [str(item.get("caption")) for item in bot.send_photos[:3]] == [
        "🏆 Turnier abgeschlossen\nPlatz #1\nPunkte: 3",
        "🏆 Turnier abgeschlossen\nPlatz #2\nPunkte: 2",
        "🏆 Turnier abgeschlossen\nPlatz #3\nPunkte: 1",
    ]

    first_batch = len(bot.send_photos)
    second = await tournaments_proof_cards.run_private_tournament_proof_cards_async(
        tournament_id=tournament_id
    )
    assert int(second["sent"]) == 3
    assert int(second["cached_reused"]) == 3
    second_batch = bot.send_photos[first_batch:]
    assert len(second_batch) == 3
    assert all(isinstance(item["photo"], str) for item in second_batch)
