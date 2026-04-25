from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from app.db.models.tournament_matches import TournamentMatch
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournament_round_scores_repo import (
    TournamentRoundScorePayload,
    TournamentRoundScoresRepo,
)
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal


async def create_completed_daily_cup_with_bye_seeded_scores(
    *,
    now_utc: datetime,
    user_ids: list[int],
) -> str:
    selected_user_ids = user_ids[:13]
    if len(selected_user_ids) != 13:
        raise ValueError("create_completed_daily_cup_with_bye_seeded_scores requires 13 users")

    round_specs: dict[int, tuple[tuple[int, int, int, bool], ...]] = {
        selected_user_ids[0]: ((2, 7, 700, False), (2, 6, 650, False), (2, 6, 600, False)),
        selected_user_ids[1]: ((2, 6, 710, False), (2, 6, 660, False), (1, 5, 610, False)),
        selected_user_ids[2]: ((2, 6, 720, False), (1, 5, 670, True), (1, 4, 620, False)),
        selected_user_ids[3]: ((2, 5, 730, False), (1, 5, 680, False), (0, 4, 630, False)),
        selected_user_ids[4]: ((1, 5, 740, False), (1, 4, 690, False), (1, 3, 640, False)),
        selected_user_ids[5]: ((2, 4, 750, False), (0, 4, 700, False), (0, 3, 650, False)),
        selected_user_ids[6]: ((1, 4, 760, False), (1, 3, 710, False), (0, 3, 660, False)),
        selected_user_ids[7]: ((1, 3, 770, False), (0, 3, 720, False), (0, 3, 670, False)),
        selected_user_ids[8]: ((1, 3, 780, False), (0, 3, 730, False), (0, 2, 680, False)),
        selected_user_ids[9]: ((0, 3, 790, False), (0, 2, 740, False), (0, 2, 690, False)),
        selected_user_ids[10]: ((0, 2, 800, False), (0, 2, 750, False), (0, 2, 700, False)),
        selected_user_ids[11]: ((0, 2, 810, False), (0, 2, 760, False), (0, 1, 710, False)),
        selected_user_ids[12]: ((0, 2, 820, False), (0, 1, 770, False), (0, 1, 720, False)),
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
                current_round=3,
                registration_deadline=now_utc - timedelta(hours=5),
                round_deadline=None,
                invite_code=uuid4().hex[:12],
                created_at=now_utc - timedelta(hours=6),
            ),
        )
        for index, user_id in enumerate(selected_user_ids):
            await TournamentParticipantsRepo.create_once(
                session,
                tournament_id=tournament.id,
                user_id=user_id,
                joined_at=now_utc - timedelta(hours=4) + timedelta(minutes=index),
            )

        session.add_all(
            [
                TournamentMatch(
                    id=uuid4(),
                    tournament_id=tournament.id,
                    round_no=1,
                    round_number=None,
                    user_a=selected_user_ids[12],
                    user_b=None,
                    bracket_slot_a=None,
                    bracket_slot_b=None,
                    friend_challenge_id=None,
                    match_timeout_task_id=None,
                    player_a_finished_at=None,
                    player_b_finished_at=None,
                    status="COMPLETED",
                    winner_id=selected_user_ids[12],
                    deadline=now_utc - timedelta(minutes=3),
                ),
                TournamentMatch(
                    id=uuid4(),
                    tournament_id=tournament.id,
                    round_no=2,
                    round_number=None,
                    user_a=selected_user_ids[2],
                    user_b=None,
                    bracket_slot_a=None,
                    bracket_slot_b=None,
                    friend_challenge_id=None,
                    match_timeout_task_id=None,
                    player_a_finished_at=None,
                    player_b_finished_at=None,
                    status="COMPLETED",
                    winner_id=selected_user_ids[2],
                    deadline=now_utc - timedelta(minutes=2),
                ),
                TournamentMatch(
                    id=uuid4(),
                    tournament_id=tournament.id,
                    round_no=3,
                    round_number=None,
                    user_a=selected_user_ids[11],
                    user_b=None,
                    bracket_slot_a=None,
                    bracket_slot_b=None,
                    friend_challenge_id=None,
                    match_timeout_task_id=None,
                    player_a_finished_at=None,
                    player_b_finished_at=None,
                    status="COMPLETED",
                    winner_id=selected_user_ids[11],
                    deadline=now_utc - timedelta(minutes=1),
                ),
            ]
        )

        for index, user_id in enumerate(selected_user_ids):
            total_points = Decimal("0")
            total_correct = Decimal("0")
            for round_number, (wins, correct_answers, total_time_ms, got_bye) in enumerate(
                round_specs[user_id], start=1
            ):
                total_points += Decimal(wins)
                total_correct += Decimal(correct_answers)
                opponent_id = None
                if not got_bye:
                    opponent_id = selected_user_ids[(index + round_number) % len(selected_user_ids)]
                    if opponent_id == user_id:
                        opponent_id = selected_user_ids[
                            (index + round_number + 1) % len(selected_user_ids)
                        ]
                await TournamentRoundScoresRepo.upsert_result(
                    session,
                    payload=TournamentRoundScorePayload(
                        tournament_id=tournament.id,
                        round_number=round_number,
                        player_id=user_id,
                        opponent_id=opponent_id,
                        wins=wins,
                        is_draw=wins == 1 and not got_bye,
                        correct_answers=correct_answers,
                        total_time_ms=total_time_ms,
                        got_bye=got_bye,
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
