from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.db.models.tournament_round_scores import TournamentRoundScore
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournament_round_scores_repo import TournamentRoundScoresRepo
from app.db.session import SessionLocal
from app.game.tournaments.daily_cup_standings import calculate_daily_cup_standings
from app.game.tournaments.settlement import settle_pending_match_from_duel
from app.workers.tasks import daily_cup_async
from tests.integration.daily_cup_test_support import (
    create_completed_daily_cup_with_participants,
    store_daily_cup_results,
    upsert_round_result,
)
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


@pytest.mark.asyncio
async def test_daily_cup_standings_use_total_time_and_handle_full_equality() -> None:
    now_utc = datetime(2026, 3, 1, 20, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_ids = [await _create_user(f"daily_cup_tie_{idx}") for idx in range(4)]
    tournament_id_str = await create_completed_daily_cup_with_participants(
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
            await upsert_round_result(
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

    await upsert_round_result(
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
            if int(row.player_id)
            in {int(auto_finished_match.user_a), int(auto_finished_match.user_b)}
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


@pytest.mark.asyncio
async def test_daily_cup_participant_totals_match_round_scores_sum() -> None:
    now_utc = datetime(2026, 3, 7, 12, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_id = await _create_user("daily_cup_totals_match_sum")
    tournament_id = UUID(
        await create_completed_daily_cup_with_participants(
            now_utc=now_utc,
            user_ids=[user_id],
        )
    )
    await store_daily_cup_results(
        now_utc=now_utc,
        tournament_id=tournament_id,
        round_results=[(1, user_id, None, 2, 5), (2, user_id, None, 1, 4)],
    )

    async with SessionLocal.begin() as session:
        participant = await TournamentParticipantsRepo.get_for_tournament_user(
            session,
            tournament_id=tournament_id,
            user_id=user_id,
        )
        totals = await TournamentRoundScoresRepo.aggregate_player_totals(
            session,
            player_id=user_id,
            tournament_id=tournament_id,
        )

        assert participant is not None
        assert participant.score == totals[0]
        assert participant.tie_break == totals[1]
        assert totals == (3, 9)


@pytest.mark.asyncio
async def test_daily_cup_idempotent_round_upsert_does_not_duplicate_participant_score() -> None:
    now_utc = datetime(2026, 3, 7, 13, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_id = await _create_user("daily_cup_idempotent_upsert")
    tournament_id = UUID(
        await create_completed_daily_cup_with_participants(
            now_utc=now_utc,
            user_ids=[user_id],
        )
    )
    await store_daily_cup_results(
        now_utc=now_utc,
        tournament_id=tournament_id,
        round_results=[(1, user_id, None, 2, 6), (1, user_id, None, 2, 6)],
    )

    async with SessionLocal.begin() as session:
        participant = await TournamentParticipantsRepo.get_for_tournament_user(
            session,
            tournament_id=tournament_id,
            user_id=user_id,
        )
        round_rows = await session.execute(
            select(func.count())
            .select_from(TournamentRoundScore)
            .where(
                TournamentRoundScore.tournament_id == tournament_id,
                TournamentRoundScore.player_id == user_id,
                TournamentRoundScore.round_number == 1,
            )
        )

        assert participant is not None
        assert participant.score == 2
        assert participant.tie_break == 6
        assert int(round_rows.scalar_one()) == 1


@pytest.mark.asyncio
async def test_daily_cup_participant_scores_do_not_mix_between_players() -> None:
    now_utc = datetime(2026, 3, 7, 14, 0, tzinfo=UTC)
    await _ensure_tournament_schema()

    user_ids = [await _create_user(f"daily_cup_isolated_totals_{idx}") for idx in range(2)]
    tournament_id = UUID(
        await create_completed_daily_cup_with_participants(
            now_utc=now_utc,
            user_ids=user_ids,
        )
    )
    await store_daily_cup_results(
        now_utc=now_utc,
        tournament_id=tournament_id,
        round_results=[
            (1, user_ids[0], user_ids[1], 2, 7),
            (1, user_ids[1], user_ids[0], 0, 3),
        ],
    )

    async with SessionLocal.begin() as session:
        first_participant = await TournamentParticipantsRepo.get_for_tournament_user(
            session,
            tournament_id=tournament_id,
            user_id=user_ids[0],
        )
        second_participant = await TournamentParticipantsRepo.get_for_tournament_user(
            session,
            tournament_id=tournament_id,
            user_id=user_ids[1],
        )

        assert first_participant is not None
        assert second_participant is not None
        assert first_participant.score == 2
        assert first_participant.tie_break == 7
        assert second_participant.score == 0
        assert second_participant.tie_break == 3
