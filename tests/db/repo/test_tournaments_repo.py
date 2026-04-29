from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.models.tournaments import Tournament
from app.db.repo.tournaments_repo import TournamentsRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


def _tournament(**overrides: object) -> Tournament:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    payload: dict[str, object] = {
        "id": uuid4(),
        "type": "DAILY_ARENA",
        "created_by": 7,
        "name": "Daily Arena",
        "status": "REGISTRATION",
        "format": "QUICK_5",
        "max_participants": 32,
        "current_round": 0,
        "registration_deadline": now_utc + timedelta(minutes=30),
        "round_deadline": None,
        "round_start_time": None,
        "bracket": None,
        "invite_code": "DAILY-20260314",
        "created_at": now_utc,
    }
    payload.update(overrides)
    return Tournament(**payload)


async def test_create_and_id_lookups_use_session_contracts() -> None:
    tournament = _tournament()
    create_session = RecordingSession()

    assert await TournamentsRepo.create(create_session, tournament=tournament) is tournament
    assert create_session.added == [tournament]
    assert create_session.flushed is True

    get_session = RecordingSession(get_result=tournament)
    assert await TournamentsRepo.get_by_id(get_session, tournament.id) is tournament
    assert get_session.get_calls == [(Tournament, tournament.id)]

    lock_session = RecordingSession(_ScalarResult(None))
    assert (
        await TournamentsRepo.get_by_id_for_update(
            lock_session,
            tournament.id,
            skip_locked=True,
        )
        is None
    )
    lock_sql = compile_statement(lock_session.statement)
    assert str(tournament.id) in lock_sql
    assert "FOR UPDATE SKIP LOCKED" in lock_sql


async def test_invite_and_registration_deadline_lookups_apply_filters() -> None:
    registration_deadline = datetime(2026, 3, 14, 12, 30, tzinfo=UTC)
    tournament = _tournament(registration_deadline=registration_deadline)

    invite_session = RecordingSession(_ScalarResult(tournament))
    assert await TournamentsRepo.get_by_invite_code(invite_session, "DAILY-20260314") is tournament
    assert "tournaments.invite_code = 'DAILY-20260314'" in compile_statement(
        invite_session.statement
    )

    invite_lock_session = RecordingSession(_ScalarResult(None))
    await TournamentsRepo.get_by_invite_code_for_update(invite_lock_session, "PRIVATE-1")
    assert "FOR UPDATE" in compile_statement(invite_lock_session.statement)

    deadline_session = RecordingSession(_ScalarResult(tournament))
    await TournamentsRepo.get_by_type_and_registration_deadline(
        deadline_session,
        tournament_type="DAILY_ARENA",
        registration_deadline=registration_deadline,
    )
    deadline_sql = compile_statement(deadline_session.statement)
    assert "tournaments.type = 'DAILY_ARENA'" in deadline_sql
    assert "tournaments.registration_deadline =" in deadline_sql

    deadline_lock_session = RecordingSession(_ScalarResult(None))
    await TournamentsRepo.get_by_type_and_registration_deadline_for_update(
        deadline_lock_session,
        tournament_type="PRIVATE",
        registration_deadline=registration_deadline,
    )
    assert "FOR UPDATE" in compile_statement(deadline_lock_session.statement)


async def test_list_due_registration_close_filters_type_and_clamps_limit() -> None:
    now_utc = datetime(2026, 3, 14, 13, 0, tzinfo=UTC)
    tournament = _tournament(registration_deadline=now_utc - timedelta(minutes=1))
    session = RecordingSession(_ScalarsResult([tournament]))

    rows = await TournamentsRepo.list_due_registration_close_for_update(
        session,
        now_utc=now_utc,
        limit=0,
        tournament_type="DAILY_ARENA",
    )

    assert rows == [tournament]
    sql = compile_statement(session.statement)
    assert "tournaments.status = 'REGISTRATION'" in sql
    assert "tournaments.registration_deadline <=" in sql
    assert "tournaments.type = 'DAILY_ARENA'" in sql
    assert "ORDER BY tournaments.registration_deadline ASC" in sql
    assert "LIMIT 1" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql


async def test_list_due_registration_close_can_run_without_type_filter() -> None:
    now_utc = datetime(2026, 3, 14, 13, 0, tzinfo=UTC)
    tournament = _tournament(registration_deadline=now_utc - timedelta(minutes=1))
    session = RecordingSession(_ScalarsResult([tournament]))

    rows = await TournamentsRepo.list_due_registration_close_for_update(
        session,
        now_utc=now_utc,
        limit=3,
    )

    assert rows == [tournament]
    sql = compile_statement(session.statement)
    assert "tournaments.status = 'REGISTRATION'" in sql
    assert "tournaments.type =" not in sql
    assert "LIMIT 3" in sql


async def test_daily_arena_round_deadline_query_accepts_match_deadline_fallbacks() -> None:
    now_utc = datetime(2026, 3, 14, 14, 0, tzinfo=UTC)
    tournament = _tournament(status="ROUND_1", current_round=1, round_deadline=None)
    session = RecordingSession(_ScalarsResult([tournament]))

    rows = await TournamentsRepo.list_due_round_deadline_for_update(
        session,
        now_utc=now_utc,
        limit=2,
        tournament_type="DAILY_ARENA",
    )

    assert rows == [tournament]
    sql = compile_statement(session.statement)
    assert "tournaments.status IN" in sql
    assert "EXISTS (SELECT tournament_matches.id" in sql
    assert "tournament_matches.status = 'PENDING'" in sql
    assert "tournament_matches.round_no = tournaments.current_round" in sql
    assert "tournaments.type = 'DAILY_ARENA'" in sql
    assert "LIMIT 2" in sql


async def test_non_daily_round_deadline_query_requires_tournament_deadline() -> None:
    now_utc = datetime(2026, 3, 14, 14, 0, tzinfo=UTC)
    tournament = _tournament(
        type="PRIVATE",
        status="BRACKET_LIVE",
        round_deadline=now_utc - timedelta(minutes=1),
    )
    session = RecordingSession(_ScalarsResult([tournament]))

    rows = await TournamentsRepo.list_due_round_deadline_for_update(
        session,
        now_utc=now_utc,
        limit=-5,
    )

    assert rows == [tournament]
    sql = compile_statement(session.statement)
    assert "tournaments.round_deadline IS NOT NULL" in sql
    assert "tournaments.round_deadline <=" in sql
    assert "EXISTS (SELECT tournament_matches.id" not in sql
    assert "LIMIT 1" in sql
