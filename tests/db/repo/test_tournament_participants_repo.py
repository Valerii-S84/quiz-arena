from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.db.models.tournament_participants import TournamentParticipant
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo as Repo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


def _participant(**overrides: object) -> TournamentParticipant:
    payload: dict[str, object] = {
        "tournament_id": uuid4(),
        "user_id": 10,
        "score": Decimal("0"),
        "tie_break": Decimal("0"),
        "joined_at": datetime(2026, 3, 14, 12, 0, tzinfo=UTC),
        "standings_message_id": None,
        "proof_card_file_id": None,
        "proof_card_sent": False,
    }
    payload.update(overrides)
    return TournamentParticipant(**payload)


async def test_create_once_inserts_defaults_and_reports_existing_participant() -> None:
    tournament_id = uuid4()
    joined_at = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)

    created_session = RecordingSession(_ScalarResult(10))
    assert (
        await Repo.create_once(
            created_session,
            tournament_id=tournament_id,
            user_id=10,
            joined_at=joined_at,
        )
        is True
    )
    created_sql = compile_statement(created_session.statement)
    assert "INSERT INTO tournament_participants" in created_sql
    assert "ON CONFLICT (tournament_id, user_id) DO NOTHING" in created_sql
    assert "RETURNING tournament_participants.user_id" in created_sql

    existing_session = RecordingSession(_ScalarResult(None))
    assert (
        await Repo.create_once(
            existing_session,
            tournament_id=tournament_id,
            user_id=10,
            joined_at=joined_at,
        )
        is False
    )


async def test_participant_count_list_and_lookup_queries_apply_ordering_and_locks() -> None:
    tournament_id = uuid4()
    participant = _participant(tournament_id=tournament_id, user_id=10)

    count_session = RecordingSession(_ScalarResult(2))
    count = await Repo.count_for_tournament(count_session, tournament_id=tournament_id)
    assert count == 2
    assert str(tournament_id) in compile_statement(count_session.statement)

    list_session = RecordingSession(_ScalarsResult([participant]))
    rows = await Repo.list_for_tournament(list_session, tournament_id=tournament_id)
    assert rows == [participant]
    list_sql = compile_statement(list_session.statement)
    assert "ORDER BY tournament_participants.score DESC" in list_sql
    assert "tournament_participants.tie_break DESC" in list_sql
    assert "tournament_participants.joined_at ASC" in list_sql
    assert "tournament_participants.user_id ASC" in list_sql

    lookup_session = RecordingSession(_ScalarResult(participant))
    assert (
        await Repo.get_for_tournament_user(
            lookup_session,
            tournament_id=tournament_id,
            user_id=10,
        )
        is participant
    )
    assert "tournament_participants.user_id = 10" in compile_statement(lookup_session.statement)

    lock_session = RecordingSession(_ScalarResult(None))
    await Repo.get_for_tournament_user_for_update(
        lock_session,
        tournament_id=tournament_id,
        user_id=10,
        skip_locked=True,
    )
    assert "FOR UPDATE SKIP LOCKED" in compile_statement(lock_session.statement)

    locked_list_session = RecordingSession(_ScalarsResult([participant]))
    await Repo.list_for_tournament_for_update(locked_list_session, tournament_id=tournament_id)
    locked_sql = compile_statement(locked_list_session.statement)
    assert "ORDER BY tournament_participants.joined_at ASC" in locked_sql
    assert "FOR UPDATE" in locked_sql


async def test_list_joined_at_by_type_filters_status_and_clamps_limit() -> None:
    joined_at = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    session = RecordingSession(_ScalarsResult([joined_at]))

    rows = await Repo.list_joined_at_for_user_by_tournament_type(
        session,
        user_id=10,
        tournament_type="DAILY_ARENA",
        tournament_status="COMPLETED",
        limit=2000,
    )

    assert rows == [joined_at]
    sql = compile_statement(session.statement)
    assert "JOIN tournaments ON tournaments.id = tournament_participants.tournament_id" in sql
    assert "tournament_participants.user_id = 10" in sql
    assert "tournaments.type = 'DAILY_ARENA'" in sql
    assert "tournaments.status = 'COMPLETED'" in sql
    assert "ORDER BY tournament_participants.joined_at DESC" in sql
    assert "LIMIT 1000" in sql


async def test_score_updates_return_affected_row_count_and_set_expected_values() -> None:
    tournament_id = uuid4()

    delta_session = RecordingSession(_ScalarResult(10))
    updated_count = await Repo.apply_score_delta(
        delta_session,
        tournament_id=tournament_id,
        user_id=10,
        score_delta=Decimal("2.5"),
        tie_break_delta=Decimal("7"),
    )
    assert updated_count == 1
    delta_sql = compile_statement(delta_session.statement)
    assert "UPDATE tournament_participants SET score=" in delta_sql
    assert "tournament_participants.score +" in delta_sql
    assert "tournament_participants.tie_break +" in delta_sql

    set_session = RecordingSession(_ScalarResult(None))
    set_count = await Repo.set_score(
        set_session,
        tournament_id=tournament_id,
        user_id=10,
        score=Decimal("12"),
        tie_break=Decimal("30"),
    )
    assert set_count == 0
    set_sql = compile_statement(set_session.statement)
    assert "score=12" in set_sql
    assert "tie_break=30" in set_sql
