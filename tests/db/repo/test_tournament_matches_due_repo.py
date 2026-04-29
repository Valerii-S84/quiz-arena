from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.models.tournament_matches import TournamentMatch
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


def _match(**overrides: object) -> TournamentMatch:
    payload: dict[str, object] = {
        "id": uuid4(),
        "tournament_id": uuid4(),
        "round_no": 1,
        "round_number": 1,
        "user_a": 10,
        "user_b": 20,
        "bracket_slot_a": 1,
        "bracket_slot_b": 2,
        "friend_challenge_id": uuid4(),
        "status": "PENDING",
        "deadline": datetime(2026, 3, 14, 12, 15, tzinfo=UTC),
    }
    payload.update(overrides)
    return TournamentMatch(**payload)


async def test_pending_match_due_queries_lock_ordered_candidates() -> None:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    tournament_id = uuid4()
    match = _match(tournament_id=tournament_id, deadline=now_utc - timedelta(seconds=1))

    due_session = RecordingSession(_ScalarsResult([match]))
    assert await TournamentMatchesRepo.list_pending_due_for_update(
        due_session,
        now_utc=now_utc,
        limit=-1,
    ) == [match]
    due_sql = compile_statement(due_session.statement)
    assert "tournament_matches.status = 'PENDING'" in due_sql
    assert "tournament_matches.deadline <=" in due_sql
    assert "LIMIT 1" in due_sql
    assert "FOR UPDATE SKIP LOCKED" in due_sql

    tournament_session = RecordingSession(_ScalarsResult([match]))
    await TournamentMatchesRepo.list_pending_for_tournament_for_update(
        tournament_session,
        tournament_id=tournament_id,
    )
    tournament_sql = compile_statement(tournament_session.statement)
    assert str(tournament_id) in tournament_sql
    assert "ORDER BY tournament_matches.round_no ASC, tournament_matches.id ASC" in tournament_sql
    assert "FOR UPDATE" in tournament_sql
