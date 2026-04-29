from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.models.tournament_matches import TournamentMatch
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult
from tests.type_helpers import build_friend_challenge

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
        "match_timeout_task_id": None,
        "player_a_finished_at": None,
        "player_b_finished_at": None,
        "status": "PENDING",
        "winner_id": None,
        "deadline": datetime(2026, 3, 14, 12, 15, tzinfo=UTC),
    }
    payload.update(overrides)
    return TournamentMatch(**payload)


async def test_create_many_short_circuits_empty_and_flushes_matches() -> None:
    empty_session = RecordingSession()
    assert await TournamentMatchesRepo.create_many(empty_session, matches=[]) == []
    assert empty_session.added_all == []
    assert empty_session.flushed is False

    match = _match()
    session = RecordingSession()
    rows = await TournamentMatchesRepo.create_many(session, matches=[match])

    assert rows == [match]
    assert session.added_all == [match]
    assert session.flushed is True


async def test_match_lookup_methods_apply_lock_and_friend_challenge_filter() -> None:
    match = _match()

    lock_session = RecordingSession(_ScalarResult(match))
    assert await TournamentMatchesRepo.get_by_id_for_update(lock_session, match.id) is match
    lock_sql = compile_statement(lock_session.statement)
    assert str(match.id) in lock_sql
    assert "FOR UPDATE" in lock_sql

    challenge_session = RecordingSession(_ScalarResult(None))
    assert match.friend_challenge_id is not None
    await TournamentMatchesRepo.get_by_friend_challenge_id(
        challenge_session,
        friend_challenge_id=match.friend_challenge_id,
    )
    assert str(match.friend_challenge_id) in compile_statement(challenge_session.statement)


async def test_match_listing_queries_keep_tournament_round_ordering() -> None:
    tournament_id = uuid4()
    match = _match(tournament_id=tournament_id)

    round_session = RecordingSession(_ScalarsResult([match]))
    assert await TournamentMatchesRepo.list_by_tournament_round(
        round_session,
        tournament_id=tournament_id,
        round_no=1,
    ) == [match]
    round_sql = compile_statement(round_session.statement)
    assert str(tournament_id) in round_sql
    assert "tournament_matches.round_no = 1" in round_sql
    assert "ORDER BY tournament_matches.deadline ASC, tournament_matches.id ASC" in round_sql

    all_session = RecordingSession(_ScalarsResult([match]))
    await TournamentMatchesRepo.list_by_tournament_for_update(
        all_session, tournament_id=tournament_id
    )
    all_sql = compile_statement(all_session.statement)
    assert "ORDER BY tournament_matches.round_no ASC, tournament_matches.id ASC" in all_sql
    assert "FOR UPDATE" in all_sql

    locked_round_session = RecordingSession(_ScalarsResult([match]))
    await TournamentMatchesRepo.list_by_tournament_round_for_update(
        locked_round_session,
        tournament_id=tournament_id,
        round_no=1,
    )
    assert "FOR UPDATE" in compile_statement(locked_round_session.statement)


async def test_round_metric_and_slot_queries_apply_expected_filters() -> None:
    tournament_id = uuid4()

    max_round_session = RecordingSession(_ScalarResult(3))
    assert (
        await TournamentMatchesRepo.get_max_round_no(
            max_round_session,
            tournament_id=tournament_id,
        )
        == 3
    )
    assert "max(tournament_matches.round_no)" in compile_statement(max_round_session.statement)

    pending_count_session = RecordingSession(_ScalarResult(None))
    assert (
        await TournamentMatchesRepo.count_pending_for_tournament_round(
            pending_count_session,
            tournament_id=tournament_id,
            round_no=2,
        )
        == 0
    )
    count_sql = compile_statement(pending_count_session.statement)
    assert "tournament_matches.round_no = 2" in count_sql
    assert "tournament_matches.status = 'PENDING'" in count_sql

    slot_session = RecordingSession(_ScalarResult(None))
    await TournamentMatchesRepo.get_by_tournament_round_slots_for_update(
        slot_session,
        tournament_id=tournament_id,
        round_number=2,
        bracket_slot_a=3,
        bracket_slot_b=4,
    )
    slot_sql = compile_statement(slot_session.statement)
    assert "tournament_matches.round_number = 2" in slot_sql
    assert "tournament_matches.bracket_slot_a = 3" in slot_sql
    assert "tournament_matches.bracket_slot_b = 4" in slot_sql
    assert "FOR UPDATE" in slot_sql


async def test_daily_cup_turn_reminder_candidates_join_match_and_challenge_state() -> None:
    now_utc = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    match = _match(deadline=now_utc + timedelta(minutes=20))
    challenge = build_friend_challenge(id=match.friend_challenge_id)
    session = RecordingSession(_RowsResult([(match, challenge)]))

    rows = await TournamentMatchesRepo.list_daily_cup_turn_reminder_candidates_for_update(
        session,
        now_utc=now_utc,
        remind_before_utc=now_utc - timedelta(minutes=5),
        limit=0,
    )

    assert rows == [(match, challenge)]
    sql = compile_statement(session.statement)
    assert "JOIN tournaments ON tournaments.id = tournament_matches.tournament_id" in sql
    assert (
        "JOIN friend_challenges ON friend_challenges.id = tournament_matches.friend_challenge_id"
        in sql
    )
    assert "tournaments.type = 'DAILY_ARENA'" in sql
    assert "friend_challenges.opponent_user_id IS NOT NULL" in sql
    assert "LIMIT 1" in sql
    assert "FOR UPDATE OF friend_challenges SKIP LOCKED" in sql
