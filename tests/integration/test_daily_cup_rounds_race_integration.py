from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from app.db.models.tournaments import Tournament
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.lifecycle import check_and_advance_round
from app.game.tournaments.service import join_daily_cup_by_id
from app.workers.tasks import daily_cup_async, daily_cup_messaging, daily_cup_rounds
from app.workers.tasks.daily_cup_time import get_daily_cup_window
from tests.integration.friend_challenge_fixtures import (
    _create_user,
    _seed_friend_challenge_questions,
)
from tests.integration.test_private_tournament_service_integration import _ensure_tournament_schema

UTC = timezone.utc


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


@pytest.mark.asyncio
async def test_concurrent_daily_cup_deadline_workers_advance_once(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    run_at = now_utc + timedelta(hours=2)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_race_worker_{idx}") for idx in range(6)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "enqueue_daily_cup_round_messaging", lambda **kwargs: None)
    started = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(started["started"]) == 1

    expired_deadline = run_at - timedelta(minutes=1)
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        tournament.round_deadline = expired_deadline
        round_one = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        assert len(round_one) == 3
        for match in round_one:
            match.deadline = expired_deadline

    enqueued_rounds: list[tuple[str, bool]] = []
    monkeypatch.setattr(daily_cup_rounds, "_now_utc", lambda: run_at)
    monkeypatch.setattr(
        daily_cup_messaging,
        "enqueue_daily_cup_round_messaging",
        lambda *, tournament_id, enqueue_completion_followups=False: enqueued_rounds.append(
            (tournament_id, bool(enqueue_completion_followups))
        ),
    )

    results = await asyncio.gather(
        daily_cup_rounds.advance_daily_cup_rounds_async(),
        daily_cup_rounds.advance_daily_cup_rounds_async(),
        daily_cup_rounds.advance_daily_cup_rounds_async(),
    )
    assert sum(int(item["rounds_started_total"]) for item in results) == 1
    assert sum(int(item["matches_created_total"]) for item in results) == 3
    assert enqueued_rounds == [(str(tournament_id), False)]

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "ROUND_2"
        assert tournament.current_round == 2
        round_one = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        round_two = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=2,
        )
        assert len(round_one) == 3
        assert len(round_two) == 3
        assert all(match.status != "PENDING" for match in round_one)


@pytest.mark.asyncio
async def test_concurrent_check_and_advance_round_starts_once(monkeypatch) -> None:
    now_utc = datetime(2026, 3, 1, 11, 0, tzinfo=UTC)
    await _ensure_tournament_schema()
    await _seed_friend_challenge_questions(now_utc=now_utc)

    user_ids = [await _create_user(f"daily_cup_race_check_{idx}") for idx in range(6)]
    tournament_id = await _create_daily_cup_registration_tournament(now_utc=now_utc)
    await _join_users(tournament_id=tournament_id, user_ids=user_ids, now_utc=now_utc)

    monkeypatch.setattr(daily_cup_async, "_now_utc", lambda: now_utc)
    monkeypatch.setattr(daily_cup_async, "enqueue_daily_cup_round_messaging", lambda **kwargs: None)
    monkeypatch.setattr(daily_cup_messaging, "enqueue_daily_cup_round_messaging", lambda **kwargs: None)
    started = await daily_cup_async.close_daily_cup_registration_and_start_async()
    assert int(started["started"]) == 1

    async with SessionLocal.begin() as session:
        round_one = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=1,
        )
        assert len(round_one) == 3
        for match in round_one:
            match.status = "COMPLETED"
            match.winner_id = int(match.user_a)

    async def _run_check_once() -> dict[str, int]:
        async with SessionLocal.begin() as session:
            return await check_and_advance_round(
                session,
                tournament_id=tournament_id,
                now_utc=now_utc + timedelta(minutes=10),
            )

    results = await asyncio.gather(_run_check_once(), _run_check_once(), _run_check_once())
    assert sum(int(item["round_started"]) for item in results) == 1
    assert sum(int(item["matches_created"]) for item in results) == 3

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id_for_update(session, tournament_id)
        assert tournament is not None
        assert tournament.status == "ROUND_2"
        assert tournament.current_round == 2
        round_two = await TournamentMatchesRepo.list_by_tournament_round(
            session,
            tournament_id=tournament_id,
            round_no=2,
        )
        assert len(round_two) == 3
