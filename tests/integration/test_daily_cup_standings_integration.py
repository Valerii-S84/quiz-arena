from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.db.models.tournament_round_scores import TournamentRoundScore
from app.db.models.tournaments import Tournament
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournament_round_scores_repo import (
    TournamentRoundScorePayload,
    TournamentRoundScoresRepo,
)
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.daily_cup_standings import calculate_daily_cup_standings
from app.game.tournaments.settlement import settle_pending_match_from_duel
from app.workers.tasks import daily_cup_async
from tests.integration.friend_challenge_fixtures import (
    _create_user,
    _seed_friend_challenge_questions,
)
from tests.integration.test_daily_cup_worker_integration import (
    _create_daily_cup_registration_tournament,
    _join_users,
)
from tests.integration.test_private_tournament_worker_integration import _ensure_tournament_schema

UTC = timezone.utc
AUTO_FINISH_MAX_TIME_MS = 2_147_483_647


async def _create_completed_daily_cup_with_participants(
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


async def _upsert_round_result(
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


@pytest.mark.asyncio
async def test_daily_cup_standings_use_total_time_and_handle_full_equality() -> None:
    now_utc = datetime(2026, 3, 1, 20, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_ids = [await _create_user(f"daily_cup_tie_{idx}") for idx in range(4)]
    tournament_id_str = await _create_completed_daily_cup_with_participants(
        now_utc=now_utc,
        user_ids=user_ids,
    )
    parsed_tournament_id = UUID(tournament_id_str)

    seeded_rounds = {
        user_ids[0]: ((2, 5, 1000), (1, 5, 1000), (1, 5, 1000), (0, 5, 1000)),
        user_ids[1]: ((2, 5, 1000), (1, 5, 1000), (1, 5, 1000), (0, 5, 2000)),
        user_ids[2]: ((2, 4, 1000), (0, 4, 1000), (1, 4, 1000), (0, 4, 1000)),
        user_ids[3]: ((1, 3, 1000), (0, 3, 1000), (1, 3, 1000), (0, 3, 1000)),
    }
    for player_id, rounds in seeded_rounds.items():
        for round_number, (points, correct_answers, total_time_ms) in enumerate(rounds, start=1):
            await _upsert_round_result(
                tournament_id=parsed_tournament_id,
                round_number=round_number,
                player_id=player_id,
                opponent_id=None,
                points=points,
                correct_answers=correct_answers,
                total_time_ms=total_time_ms,
                is_draw=points == 1,
            )

    async with SessionLocal.begin() as session:
        standings = await calculate_daily_cup_standings(session, tournament_id=parsed_tournament_id)

    assert [item.user_id for item in standings[:2]] == [user_ids[0], user_ids[1]]
    assert [(item.wins, item.correct_answers, item.total_time_ms) for item in standings[:2]] == [
        (4, 20, 4000),
        (4, 20, 5000),
    ]

    await _upsert_round_result(
        tournament_id=parsed_tournament_id,
        round_number=4,
        player_id=user_ids[1],
        opponent_id=None,
        points=0,
        correct_answers=5,
        total_time_ms=1000,
        is_draw=False,
    )

    async with SessionLocal.begin() as session:
        standings = await calculate_daily_cup_standings(session, tournament_id=parsed_tournament_id)

    assert [item.user_id for item in standings[:4]] == user_ids
    assert standings[0].wins == standings[1].wins == 4
    assert standings[0].correct_answers == standings[1].correct_answers == 20
    assert standings[0].total_time_ms == standings[1].total_time_ms == 4000
    assert [item.place for item in standings] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_daily_cup_auto_finish_uses_max_time_and_ranks_below_completed_loss(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 3, 6, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_auto_finish_{idx}") for idx in range(4)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(
        daily_cup_async,
        "enqueue_daily_cup_round_messaging",
        lambda *, tournament_id: None,
    )
    started = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(started["started"]) == 1

    async with SessionLocal.begin() as session:
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        assert len(matches) == 2
        auto_finished_match = matches[0]
        completed_match = matches[1]

        auto_finished_match.deadline = now_utc - timedelta(minutes=1)
        auto_settled = await settle_pending_match_from_duel(
            session,
            match=auto_finished_match,
            now_utc=now_utc,
        )
        assert auto_settled is True

        assert completed_match.friend_challenge_id is not None
        completed_challenge = await FriendChallengesRepo.get_by_id_for_update(
            session,
            completed_match.friend_challenge_id,
        )
        assert completed_challenge is not None
        completed_challenge.status = "COMPLETED"
        completed_challenge.winner_user_id = int(completed_match.user_b)
        completed_challenge.creator_score = 0
        completed_challenge.opponent_score = 1
        completed_challenge.creator_finished_at = now_utc
        completed_challenge.opponent_finished_at = now_utc
        completed_challenge.completed_at = now_utc
        completed_challenge.updated_at = now_utc

        completed_settled = await settle_pending_match_from_duel(
            session,
            match=completed_match,
            now_utc=now_utc,
        )
        assert completed_settled is True

        round_rows = list(
            (
                await session.execute(
                    select(TournamentRoundScore).where(
                        TournamentRoundScore.tournament_id == tournament_id,
                        TournamentRoundScore.round_number == 1,
                    )
                )
            ).scalars()
        )
        auto_rows = [
            row
            for row in round_rows
            if int(row.player_id) in {int(auto_finished_match.user_a), int(auto_finished_match.user_b)}
        ]
        assert len(auto_rows) == 2
        assert all(int(row.total_time_ms) == AUTO_FINISH_MAX_TIME_MS for row in auto_rows)
        assert all(bool(row.auto_finished) is True for row in auto_rows)

        standings = await calculate_daily_cup_standings(session, tournament_id=tournament_id)

    completed_loser_id = int(completed_match.user_a)
    zero_point_user_ids = [
        item.user_id for item in standings if item.wins == 0 and item.correct_answers == 0
    ]
    assert completed_loser_id in zero_point_user_ids
    assert zero_point_user_ids.index(completed_loser_id) == 0
    assert zero_point_user_ids[1:] == [
        int(auto_finished_match.user_a),
        int(auto_finished_match.user_b),
    ]
