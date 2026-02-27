from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournament_participants import TournamentParticipant
from app.db.models.tournaments import Tournament
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal, engine
from app.game.tournaments.service import (
    create_private_tournament,
    join_private_tournament_by_code,
    start_private_tournament,
)
from tests.integration.friend_challenge_fixtures import (
    _create_user,
    _seed_friend_challenge_questions,
)

UTC = timezone.utc


async def _ensure_tournament_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Tournament.__table__.create, checkfirst=True)
        await conn.run_sync(TournamentParticipant.__table__.create, checkfirst=True)
        await conn.run_sync(TournamentMatch.__table__.create, checkfirst=True)


@pytest.mark.asyncio
async def test_private_tournament_create_join_and_start_creates_round_one_duels() -> None:
    now_utc = datetime.now(UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    creator_user_id = await _create_user("private_tournament_creator")
    user_2 = await _create_user("private_tournament_user_2")
    user_3 = await _create_user("private_tournament_user_3")
    user_4 = await _create_user("private_tournament_user_4")

    async with SessionLocal.begin() as session:
        tournament = await create_private_tournament(
            session,
            created_by=creator_user_id,
            format_code="QUICK_5",
            now_utc=now_utc,
            name="Freunde Abend",
        )
        invite_code = tournament.invite_code
        await join_private_tournament_by_code(
            session,
            user_id=user_2,
            invite_code=invite_code,
            now_utc=now_utc,
        )
        await join_private_tournament_by_code(
            session,
            user_id=user_3,
            invite_code=invite_code,
            now_utc=now_utc,
        )
        await join_private_tournament_by_code(
            session,
            user_id=user_4,
            invite_code=invite_code,
            now_utc=now_utc,
        )
        started = await start_private_tournament(
            session,
            creator_user_id=creator_user_id,
            tournament_id=tournament.tournament_id,
            now_utc=now_utc,
        )
        assert started.round_no == 1
        assert started.matches_total == 2

        tournament_row = await TournamentsRepo.get_by_id_for_update(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert tournament_row is not None
        assert tournament_row.status == "ROUND_1"
        assert tournament_row.current_round == 1
        assert tournament_row.round_deadline is not None

        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=tournament.tournament_id,
        )
        assert len(participants) == 4

        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament.tournament_id,
            round_no=1,
        )
        assert len(matches) == 2
        for match in matches:
            assert match.status == "PENDING"
            assert match.friend_challenge_id is not None
            challenge = await FriendChallengesRepo.get_by_id_for_update(
                session,
                match.friend_challenge_id,
            )
            assert challenge is not None
            assert challenge.tournament_match_id == match.id
            assert challenge.status == "ACCEPTED"
            assert challenge.total_rounds == 5
            assert challenge.opponent_user_id is not None


@pytest.mark.asyncio
async def test_private_tournament_start_with_odd_participants_creates_walkover_bye() -> None:
    now_utc = datetime.now(UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    creator_user_id = await _create_user("private_tournament_odd_creator")
    user_2 = await _create_user("private_tournament_odd_user_2")
    user_3 = await _create_user("private_tournament_odd_user_3")

    async with SessionLocal.begin() as session:
        tournament = await create_private_tournament(
            session,
            created_by=creator_user_id,
            format_code="QUICK_12",
            now_utc=now_utc,
        )
        invite_code = tournament.invite_code
        await join_private_tournament_by_code(
            session,
            user_id=user_2,
            invite_code=invite_code,
            now_utc=now_utc,
        )
        await join_private_tournament_by_code(
            session,
            user_id=user_3,
            invite_code=invite_code,
            now_utc=now_utc,
        )
        started = await start_private_tournament(
            session,
            creator_user_id=creator_user_id,
            tournament_id=tournament.tournament_id,
            now_utc=now_utc,
        )
        assert started.matches_total == 2

        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament.tournament_id,
            round_no=1,
        )
        assert len(matches) == 2
        walkovers = [match for match in matches if match.status == "WALKOVER"]
        pending = [match for match in matches if match.status == "PENDING"]
        assert len(walkovers) == 1
        assert len(pending) == 1
        assert walkovers[0].winner_id == walkovers[0].user_a

        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=tournament.tournament_id,
        )
        top_score = max(float(item.score) for item in participants)
        assert top_score >= 1.0
