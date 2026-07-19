from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.db.models.users import User
from app.db.repo.users_repo import UsersRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


async def test_user_lookup_methods_use_expected_keys_and_filters() -> None:
    user = User(id=7, telegram_user_id=70, referral_code="REF7", status="ACTIVE")
    get_session = RecordingSession(get_result=user)

    assert await UsersRepo.get_by_id(get_session, 7) is user
    assert get_session.get_calls == [(User, 7)]

    lock_session = RecordingSession(_ScalarResult(None))
    assert await UsersRepo.get_by_id_for_update(lock_session, 7) is None
    assert lock_session.statement is not None
    assert "users.id = 7" in compile_statement(lock_session.statement)
    assert "FOR UPDATE" in compile_statement(lock_session.statement)

    telegram_session = RecordingSession(_ScalarResult(None))
    assert await UsersRepo.get_by_telegram_user_id(telegram_session, 700) is None
    assert telegram_session.statement is not None
    assert "users.telegram_user_id = 700" in compile_statement(telegram_session.statement)

    telegram_id_session = RecordingSession(_ScalarResult(7))
    assert await UsersRepo.get_id_by_telegram_user_id(telegram_id_session, 700) == 7
    assert telegram_id_session.statement is not None
    telegram_id_sql = compile_statement(telegram_id_session.statement)
    assert "SELECT users.id" in telegram_id_sql
    assert "users.telegram_user_id = 700" in telegram_id_sql

    referral_session = RecordingSession(_ScalarResult(user))
    assert await UsersRepo.get_by_referral_code(referral_session, "REF7") is user
    assert referral_session.statement is not None
    assert "users.referral_code = 'REF7'" in compile_statement(referral_session.statement)


async def test_list_by_ids_short_circuits_empty_and_deduplicates_ids() -> None:
    no_execute_session = RecordingSession()
    assert await UsersRepo.list_by_ids(no_execute_session, []) == []
    assert no_execute_session.statements == []

    user = User(id=5, telegram_user_id=50, referral_code="REF5", status="ACTIVE")
    session = RecordingSession(_ScalarsResult([user]))

    rows = await UsersRepo.list_by_ids(session, [5, 5])

    assert rows == [user]
    assert session.statement is not None
    assert "users.id IN (5)" in compile_statement(session.statement)


async def test_create_touch_and_global_streak_paths_use_session_contracts() -> None:
    create_session = RecordingSession()
    created = await UsersRepo.create(
        create_session,
        telegram_user_id=123,
        referral_code="REF123",
        username="tester",
        first_name="Tess",
        referred_by_user_id=9,
    )

    assert create_session.added == [created]
    assert create_session.flushed is True
    assert created.status == "ACTIVE"
    assert created.language_code == "de"
    assert created.timezone == "Europe/Berlin"
    assert created.referred_by_user_id == 9

    seen_at = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    touch_session = RecordingSession(SimpleNamespace(rowcount=2))
    assert await UsersRepo.touch_last_seen(touch_session, 123, seen_at) == 2
    assert touch_session.statement is not None
    touch_sql = compile_statement(touch_session.statement)
    assert "UPDATE users SET last_seen_at=" in touch_sql
    assert "users.id = 123" in touch_sql

    touch_by_telegram_session = RecordingSession(_ScalarResult(created))
    assert (
        await UsersRepo.touch_last_seen_by_telegram_user_id(
            touch_by_telegram_session,
            123,
            seen_at,
        )
        is created
    )
    assert touch_by_telegram_session.statement is not None
    touch_by_telegram_sql = compile_statement(touch_by_telegram_session.statement)
    assert "UPDATE users SET last_seen_at=" in touch_by_telegram_sql
    assert "users.telegram_user_id = 123" in touch_by_telegram_sql
    assert "RETURNING users.id" in touch_by_telegram_sql

    streak_session = RecordingSession(_ScalarResult(11))
    assert await UsersRepo.get_global_best_streak(streak_session) == 11
    assert streak_session.statement is not None
    assert "max(streak_state.best_streak)" in compile_statement(streak_session.statement)


async def test_list_daily_push_targets_filters_completed_and_logged_users() -> None:
    session = RecordingSession(_RowsResult([("8", "800", "4")]))

    rows = await UsersRepo.list_daily_push_targets(
        session,
        berlin_date=date(2026, 3, 14),
        push_kind="DAILY_MORNING",
        after_user_id=7,
        limit=5000,
    )

    assert rows == [(8, 800, 4)]
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "users.status = 'ACTIVE'" in sql
    assert "daily_runs.status = 'COMPLETED'" in sql
    assert "daily_push_logs.push_kind = 'DAILY_MORNING'" in sql
    assert "users.id > 7" in sql
    assert "LIMIT 1000" in sql


async def test_list_daily_cup_push_targets_filters_recent_unregistered_users() -> None:
    tournament_id = uuid4()
    session = RecordingSession(_RowsResult([("9", "900")]))

    rows = await UsersRepo.list_daily_cup_push_targets(
        session,
        tournament_id=tournament_id,
        active_since_utc=datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
        after_user_id=8,
        limit=0,
    )

    assert rows == [(9, 900)]
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert str(tournament_id) in sql
    assert "users.last_seen_at IS NOT NULL" in sql
    assert "users.id > 8" in sql
    assert "LIMIT 1" in sql


async def test_list_daily_cup_registered_reminder_targets_uses_join_and_clamped_limit() -> None:
    tournament_id = uuid4()
    session = RecordingSession(_RowsResult([(10, 1000)]))

    rows = await UsersRepo.list_daily_cup_registered_reminder_targets(
        session,
        tournament_id=tournament_id,
        after_user_id=9,
        limit=1500,
    )

    assert rows == [(10, 1000)]
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "JOIN tournament_participants" in sql
    assert str(tournament_id) in sql
    assert "users.last_seen_at IS NULL" in sql
    assert "users.last_seen_at <= tournament_participants.joined_at" in sql
    assert "users.id > 9" in sql
    assert "LIMIT 1000" in sql
