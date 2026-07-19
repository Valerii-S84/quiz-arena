from __future__ import annotations

from uuid import uuid4

from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo as Repo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult as _ScalarResult


async def test_participant_metadata_updates_reuse_scoped_update_helper() -> None:
    tournament_id = uuid4()

    missing_message_session = RecordingSession(_ScalarResult(10))
    assert (
        await Repo.set_standings_message_id_if_missing(
            missing_message_session,
            tournament_id=tournament_id,
            user_id=10,
            message_id=555,
        )
        == 1
    )
    missing_message_sql = compile_statement(missing_message_session.statement)
    assert "standings_message_id=555" in missing_message_sql
    assert "tournament_participants.standings_message_id IS NULL" in missing_message_sql

    message_session = RecordingSession(_ScalarResult(10))
    await Repo.set_standings_message_id(
        message_session,
        tournament_id=tournament_id,
        user_id=10,
        message_id=777,
    )
    assert "standings_message_id=777" in compile_statement(message_session.statement)

    fenced_message_session = RecordingSession(_ScalarResult(10))
    await Repo.compare_and_set_standings_message_id(
        fenced_message_session,
        tournament_id=tournament_id,
        user_id=10,
        expected_message_id=777,
        message_id=888,
        expected_status="ROUND_2",
        expected_round=2,
    )
    fenced_message_sql = compile_statement(fenced_message_session.statement)
    assert "tournament_participants.standings_message_id = 777" in fenced_message_sql
    assert "tournaments.status = 'ROUND_2'" in fenced_message_sql
    assert "tournaments.current_round = 2" in fenced_message_sql

    proof_session = RecordingSession(_ScalarResult(10))
    await Repo.set_proof_card_file_id_if_missing(
        proof_session,
        tournament_id=tournament_id,
        user_id=10,
        file_id="proof-file",
    )
    proof_sql = compile_statement(proof_session.statement)
    assert "proof_card_file_id='proof-file'" in proof_sql
    assert "tournament_participants.proof_card_file_id IS NULL" in proof_sql

    sent_session = RecordingSession(_ScalarResult(10))
    await Repo.set_proof_card_sent(sent_session, tournament_id=tournament_id, user_id=10)
    assert "proof_card_sent=true" in compile_statement(sent_session.statement)
