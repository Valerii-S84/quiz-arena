from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


async def test_non_daily_round_deadline_can_filter_by_tournament_type() -> None:
    now_utc = datetime(2026, 3, 14, 14, 0, tzinfo=UTC)
    tournament = object()
    session = RecordingSession(_ScalarsResult([tournament]))

    rows = await TournamentsRepo.list_due_round_deadline_for_update(
        session,
        now_utc=now_utc,
        limit=4,
        tournament_type="PRIVATE",
    )

    assert rows == [tournament]
    sql = compile_statement(session.statement)
    assert "tournaments.round_deadline IS NOT NULL" in sql
    assert "tournaments.type = 'PRIVATE'" in sql
    assert "EXISTS (SELECT tournament_matches.id" not in sql
    assert "LIMIT 4" in sql


async def test_match_max_round_defaults_to_zero_when_tournament_has_no_matches() -> None:
    tournament_id = uuid4()
    session = RecordingSession(_ScalarResult(None))

    max_round = await TournamentMatchesRepo.get_max_round_no(
        session,
        tournament_id=tournament_id,
    )

    assert max_round == 0
    sql = compile_statement(session.statement)
    assert "max(tournament_matches.round_no)" in sql
    assert str(tournament_id) in sql


async def test_pending_match_count_returns_database_count() -> None:
    tournament_id = uuid4()
    session = RecordingSession(_ScalarResult(5))

    count = await TournamentMatchesRepo.count_pending_for_tournament_round(
        session,
        tournament_id=tournament_id,
        round_no=3,
    )

    assert count == 5
    sql = compile_statement(session.statement)
    assert "tournament_matches.round_no = 3" in sql
    assert "tournament_matches.status = 'PENDING'" in sql


async def test_participant_count_defaults_to_zero_for_empty_tournament() -> None:
    tournament_id = uuid4()
    session = RecordingSession(_ScalarResult(None))

    count = await TournamentParticipantsRepo.count_for_tournament(
        session,
        tournament_id=tournament_id,
    )

    assert count == 0
    assert str(tournament_id) in compile_statement(session.statement)
