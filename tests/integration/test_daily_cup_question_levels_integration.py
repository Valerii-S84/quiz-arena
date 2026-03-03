from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.db.models.quiz_questions import QuizQuestion
from app.db.models.tournaments import Tournament
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.quiz_questions_repo import QuizQuestionsRepo
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.service import join_daily_cup_by_id
from app.workers.tasks import daily_cup_async, daily_cup_rounds
from app.workers.tasks.daily_cup_time import get_daily_cup_window
from tests.integration.friend_challenge_fixtures import (
    _create_user,
    _seed_friend_challenge_questions,
)
from tests.integration.test_private_tournament_service_integration import _ensure_tournament_schema

UTC = timezone.utc


def _build_b2_question(*, question_id: str, now_utc: datetime) -> QuizQuestion:
    return QuizQuestion(
        question_id=question_id,
        mode_code="QUICK_MIX_A1A2",
        source_file="daily_cup_b2_seed.csv",
        level="B2",
        category="DailyCupB2",
        question_text=f"B2 Frage {question_id}?",
        option_1="A",
        option_2="B",
        option_3="C",
        option_4="D",
        correct_option_id=0,
        correct_answer="A",
        explanation="Seed",
        key=question_id,
        status="ACTIVE",
        created_at=now_utc,
        updated_at=now_utc,
    )


async def _seed_daily_cup_b2_questions(*, now_utc: datetime) -> None:
    records = [
        _build_b2_question(question_id=f"fc_b2_{idx:03d}", now_utc=now_utc) for idx in range(1, 7)
    ]
    async with SessionLocal.begin() as session:
        session.add_all(records)
        await session.flush()


async def _create_daily_cup_registration_tournament(*, now_utc: datetime) -> UUID:
    window = get_daily_cup_window(now_utc=now_utc)
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.create(
            session,
            tournament=Tournament(
                id=uuid4(),
                type="DAILY_ARENA",
                created_by=None,
                name="Daily Arena Cup",
                status="REGISTRATION",
                format="QUICK_5",
                max_participants=8,
                current_round=0,
                registration_deadline=window.close_at_utc,
                round_deadline=None,
                invite_code=uuid4().hex[:12],
                created_at=now_utc,
            ),
        )
        return tournament.id


async def _join_users(*, tournament_id: UUID, user_ids: list[int], now_utc: datetime) -> None:
    async with SessionLocal.begin() as session:
        for user_id in user_ids:
            await join_daily_cup_by_id(
                session,
                user_id=user_id,
                tournament_id=tournament_id,
                now_utc=now_utc,
            )


async def _assert_round_question_levels(
    *,
    tournament_id: UUID,
    round_no: int,
    expected_levels: tuple[str, ...],
) -> None:
    async with SessionLocal.begin() as session:
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=round_no,
        )
        assert len(matches) == 3
        for match in matches:
            assert match.friend_challenge_id is not None
            challenge = await FriendChallengesRepo.get_by_id(session, match.friend_challenge_id)
            assert challenge is not None
            assert challenge.question_ids is not None
            ordered_question_ids = [str(question_id) for question_id in challenge.question_ids]
            question_rows = await QuizQuestionsRepo.list_by_ids(
                session,
                question_ids=ordered_question_ids,
            )
            levels_by_question_id = {row.question_id: row.level for row in question_rows}
            resolved_levels = tuple(
                levels_by_question_id[question_id] for question_id in ordered_question_ids
            )
            assert resolved_levels == expected_levels


async def _expire_round_and_advance(
    *,
    tournament_id: UUID,
    round_no: int,
    run_at: datetime,
    monkeypatch,
) -> None:
    expired_deadline = run_at - timedelta(minutes=1)
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        tournament.round_deadline = expired_deadline
        matches = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=round_no,
        )
        assert len(matches) == 3
        for match in matches:
            match.deadline = expired_deadline
    monkeypatch.setattr(daily_cup_rounds, "_now_utc", lambda: run_at)
    await daily_cup_rounds.advance_daily_cup_rounds_async()


@pytest.mark.asyncio
async def test_daily_cup_round_2_and_3_question_level_mix(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)
    await _seed_daily_cup_b2_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_levels_{idx}") for idx in range(6)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    await daily_cup_async.close_daily_cup_registration_and_start_async()

    await _assert_round_question_levels(
        tournament_id=tournament_id,
        round_no=1,
        expected_levels=("A1", "A1", "A1", "A2", "A2"),
    )

    await _expire_round_and_advance(
        tournament_id=tournament_id,
        round_no=1,
        run_at=now_utc + timedelta(hours=2),
        monkeypatch=monkeypatch,
    )
    await _assert_round_question_levels(
        tournament_id=tournament_id,
        round_no=2,
        expected_levels=("A2", "A2", "A2", "A2", "A2"),
    )

    await _expire_round_and_advance(
        tournament_id=tournament_id,
        round_no=2,
        run_at=now_utc + timedelta(hours=3),
        monkeypatch=monkeypatch,
    )
    await _assert_round_question_levels(
        tournament_id=tournament_id,
        round_no=3,
        expected_levels=("A2", "B1", "B1", "B1", "B2"),
    )

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "ROUND_3"
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=tournament_id,
        )
        assert len(participants) == 6
