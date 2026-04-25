from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.sessions.service.friend_challenges_tournament_progress import (
    handle_tournament_duel_progress,
)
from app.workers.tasks import daily_cup_async
from tests.integration.friend_challenge_fixtures import (
    _create_user,
    _seed_friend_challenge_questions,
)
from tests.integration.test_daily_cup_worker_integration import (
    _create_daily_cup_registration_tournament,
    _join_users,
)
from tests.integration.test_private_tournament_service_integration import _ensure_tournament_schema

UTC = timezone.utc


async def _start_daily_cup(*, monkeypatch, now_utc: datetime) -> UUID:
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_round_deadline_{idx}") for idx in range(4)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "enqueue_daily_cup_round_messaging", lambda **kwargs: None)

    result = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(result["started"]) == 1
    return tournament_id


@pytest.mark.asyncio
async def test_first_finished_daily_cup_match_does_not_shrink_shared_round_deadline(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 3, 7, 11, 0, tzinfo=UTC)
    progress_time = now_utc + timedelta(minutes=5)
    tournament_id = await _start_daily_cup(monkeypatch=monkeypatch, now_utc=now_utc)

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        original_round_deadline = tournament.round_deadline
        assert original_round_deadline is not None

        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        match = next(item for item in matches if item.user_b is not None)
        original_match_deadline = match.deadline
        assert original_match_deadline == original_round_deadline
        assert match.friend_challenge_id is not None

        challenge = await FriendChallengesRepo.get_by_id_for_update(
            session, match.friend_challenge_id
        )
        assert challenge is not None
        challenge.creator_score = 4
        challenge.creator_answered_round = challenge.total_rounds
        challenge.creator_finished_at = progress_time
        challenge.status = "CREATOR_DONE"
        challenge.updated_at = progress_time

        await handle_tournament_duel_progress(
            session,
            challenge=challenge,
            user_id=int(challenge.creator_user_id),
            now_utc=progress_time,
        )

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.round_deadline == original_round_deadline

        refreshed_matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        refreshed_match = next(item for item in refreshed_matches if item.user_b is not None)
        assert refreshed_match.deadline == progress_time + timedelta(minutes=15)
