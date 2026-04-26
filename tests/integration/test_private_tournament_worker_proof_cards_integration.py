from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

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
from tests.type_helpers import as_any_dict

UTC = timezone.utc


async def _create_completed_private_tournament(
    *,
    now_utc: datetime,
    seed_prefix: str,
) -> tuple[str, int]:
    creator_user_id = await _create_user(f"{seed_prefix}_creator")
    user_2 = await _create_user(f"{seed_prefix}_user_2")
    user_3 = await _create_user(f"{seed_prefix}_user_3")

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
        participants[0].score = Decimal("3")
        participants[1].score = Decimal("2")
        participants[2].score = Decimal("1")

        tournament_row = await TournamentsRepo.get_by_id_for_update(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert tournament_row is not None
        tournament_row.status = "COMPLETED"
        tournament_row.current_round = 3
        return str(tournament.tournament_id), creator_user_id


@pytest.mark.asyncio
async def test_duplicate_auto_runs_do_not_resend_private_proof_cards(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
    await _ensure_tournament_schema()
    tournament_id, _ = await _create_completed_private_tournament(
        now_utc=now_utc,
        seed_prefix="private_tournament_proof_auto",
    )

    bot = _DummyWorkerBot()
    monkeypatch.setattr(tournaments_proof_cards, "build_bot", lambda: bot)

    first = as_any_dict(
        await tournaments_proof_cards.run_private_tournament_proof_cards_async(
            tournament_id=tournament_id
        )
    )
    assert int(first["sent"]) == 3
    assert int(first["cached_reused"]) == 0
    assert all(not isinstance(item["photo"], str) for item in bot.send_photos)
    assert [str(item.get("caption")) for item in bot.send_photos[:3]] == [
        "🏆 Turnier abgeschlossen\nPlatz #1\nPunkte: 3",
        "🏆 Turnier abgeschlossen\nPlatz #2\nPunkte: 2",
        "🏆 Turnier abgeschlossen\nPlatz #3\nPunkte: 1",
    ]
    async with SessionLocal.begin() as session:
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=UUID(tournament_id),
        )
        assert all(item.proof_card_sent is True for item in participants)
        assert all(item.proof_card_file_id is not None for item in participants)

    first_batch = len(bot.send_photos)
    second = as_any_dict(
        await tournaments_proof_cards.run_private_tournament_proof_cards_async(
            tournament_id=tournament_id
        )
    )
    assert int(second["sent"]) == 0
    assert int(second["cached_reused"]) == 0
    assert bot.send_photos[first_batch:] == []


@pytest.mark.asyncio
async def test_explicit_resend_uses_cached_private_proof_card_file_id(monkeypatch) -> None:
    now_utc = datetime.now(UTC)
    await _ensure_tournament_schema()
    tournament_id, creator_user_id = await _create_completed_private_tournament(
        now_utc=now_utc,
        seed_prefix="private_tournament_proof_resend",
    )

    bot = _DummyWorkerBot()
    monkeypatch.setattr(tournaments_proof_cards, "build_bot", lambda: bot)

    first = as_any_dict(
        await tournaments_proof_cards.run_private_tournament_proof_cards_async(
            tournament_id=tournament_id
        )
    )
    assert int(first["sent"]) == 3
    first_batch = len(bot.send_photos)

    resend = as_any_dict(
        await tournaments_proof_cards.run_private_tournament_proof_cards_async(
            tournament_id=tournament_id,
            user_id=creator_user_id,
        )
    )
    assert int(resend["sent"]) == 1
    assert int(resend["cached_reused"]) == 1
    resend_batch = bot.send_photos[first_batch:]
    assert len(resend_batch) == 1
    assert isinstance(resend_batch[0]["photo"], str)
