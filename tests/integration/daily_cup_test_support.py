from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournament_round_scores_repo import (
    TournamentRoundScorePayload,
    TournamentRoundScoresRepo,
)
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.daily_cup_scoring import (
    DailyCupPlayerResult,
    store_daily_cup_player_result,
)

UTC = timezone.utc


async def create_completed_daily_cup_with_participants(
    *,
    now_utc: datetime,
    user_ids: list[int],
) -> str:
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
                registration_deadline=now_utc,
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
                joined_at=now_utc + timedelta(minutes=index),
            )
        return str(tournament.id)


async def upsert_round_result(
    *,
    tournament_id: UUID,
    round_number: int,
    player_id: int,
    opponent_id: int | None,
    points: int,
    correct_answers: int,
    total_time_ms: int,
    is_draw: bool = False,
) -> None:
    async with SessionLocal.begin() as session:
        await TournamentRoundScoresRepo.upsert_result(
            session,
            payload=TournamentRoundScorePayload(
                tournament_id=tournament_id,
                round_number=round_number,
                player_id=player_id,
                opponent_id=opponent_id,
                wins=points,
                is_draw=is_draw,
                correct_answers=correct_answers,
                total_time_ms=total_time_ms,
                got_bye=False,
                auto_finished=False,
                created_at=datetime(2026, 3, 1, 20, 0, tzinfo=UTC),
            ),
        )


def build_daily_cup_match(
    *,
    tournament_id: UUID,
    round_number: int,
    user_a: int,
    user_b: int | None,
    deadline: datetime,
) -> TournamentMatch:
    return TournamentMatch(
        id=uuid4(),
        tournament_id=tournament_id,
        round_no=round_number,
        round_number=None,
        user_a=user_a,
        user_b=user_b,
        bracket_slot_a=None,
        bracket_slot_b=None,
        friend_challenge_id=None,
        match_timeout_task_id=None,
        player_a_finished_at=None,
        player_b_finished_at=None,
        status="COMPLETED",
        winner_id=user_a if user_b is None else None,
        deadline=deadline,
    )


async def store_daily_cup_results(
    *,
    now_utc: datetime,
    tournament_id: UUID,
    round_results: list[tuple[int, int, int | None, int, int]],
) -> None:
    async with SessionLocal.begin() as session:
        for round_number, player_id, opponent_id, wins, correct_answers in round_results:
            await store_daily_cup_player_result(
                session,
                match=build_daily_cup_match(
                    tournament_id=tournament_id,
                    round_number=round_number,
                    user_a=player_id,
                    user_b=opponent_id,
                    deadline=now_utc + timedelta(minutes=round_number),
                ),
                result=DailyCupPlayerResult(
                    player_id=player_id,
                    opponent_id=opponent_id,
                    wins=wins,
                    correct_answers=correct_answers,
                    total_time_ms=1000 * round_number,
                    is_draw=wins == 1,
                    auto_finished=False,
                    got_bye=False,
                ),
                created_at=now_utc,
            )
