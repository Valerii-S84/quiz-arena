from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from app.db.repo import promo_repo_attempts, promo_repo_codes, promo_repo_redemptions
from app.db.repo.users_repo import UsersRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult
from tests.type_helpers import build_promo_code, build_promo_redemption

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)


async def test_user_push_queries_allow_initial_pages_without_after_filters() -> None:
    daily_session = RecordingSession(_RowsResult([(1, 100, 0)]))
    assert await UsersRepo.list_daily_push_targets(
        daily_session,
        berlin_date=date(2026, 3, 14),
        push_kind="DAILY_MORNING",
        after_user_id=None,
        limit=0,
    ) == [(1, 100, 0)]
    daily_sql = compile_statement(daily_session.statement)
    assert "users.id >" not in daily_sql
    assert "LIMIT 1" in daily_sql

    cup_session = RecordingSession(_RowsResult([(2, 200)]))
    await UsersRepo.list_daily_cup_push_targets(
        cup_session,
        tournament_id=uuid4(),
        active_since_utc=NOW_UTC - timedelta(hours=1),
        after_user_id=None,
        limit=1500,
    )
    cup_sql = compile_statement(cup_session.statement)
    assert "users.id >" not in cup_sql
    assert "LIMIT 1000" in cup_sql

    reminder_session = RecordingSession(_RowsResult([(3, 300)]))
    await UsersRepo.list_daily_cup_registered_reminder_targets(
        reminder_session,
        tournament_id=uuid4(),
        after_user_id=None,
        limit=2,
    )
    reminder_sql = compile_statement(reminder_session.statement)
    assert "users.id >" not in reminder_sql
    assert "LIMIT 2" in reminder_sql


async def test_promo_code_listing_allows_unfiltered_queries() -> None:
    promo = build_promo_code(id=81)
    session = RecordingSession(_ScalarsResult([promo]))

    rows = await promo_repo_codes.list_codes(
        session,
        status=None,
        campaign_name=None,
        limit=10,
    )

    assert rows == [promo]
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "WHERE" not in sql
    assert "ORDER BY promo_codes.updated_at DESC, promo_codes.id DESC" in sql
    assert "LIMIT 10" in sql


async def test_promo_attempt_queries_allow_missing_result_filters() -> None:
    count_session = RecordingSession(_ScalarResult(3))
    assert (
        await promo_repo_attempts.count_user_attempts(
            count_session,
            user_id=7,
            since_utc=NOW_UTC,
            attempt_results=None,
        )
        == 3
    )
    count_sql = compile_statement(count_session.statement)
    assert "promo_attempts.user_id = 7" in count_sql
    assert "promo_attempts.result IN" not in count_sql

    last_session = RecordingSession(_ScalarResult(NOW_UTC))
    assert (
        await promo_repo_attempts.get_last_user_attempt_at(
            last_session,
            user_id=7,
            since_utc=NOW_UTC,
            attempt_results=None,
        )
        == NOW_UTC
    )
    last_sql = compile_statement(last_session.statement)
    assert "max(promo_attempts.attempted_at)" in last_sql
    assert "promo_attempts.result IN" not in last_sql


async def test_reserved_redemption_count_without_exclusion_omits_id_predicate() -> None:
    session = RecordingSession(_ScalarResult(2))

    assert (
        await promo_repo_redemptions.count_active_reserved_redemptions(
            session,
            promo_code_id=21,
            now_utc=NOW_UTC,
            exclude_redemption_id=None,
        )
        == 2
    )

    sql = compile_statement(session.statement)
    assert "promo_redemptions.promo_code_id = 21" in sql
    assert "promo_redemptions.id !=" not in sql


async def test_revoke_redemption_for_refund_keeps_already_revoked_redemption_unchanged() -> None:
    purchase_id = uuid4()
    old_updated_at = NOW_UTC - timedelta(days=1)
    redemption = build_promo_redemption(
        status="REVOKED",
        applied_purchase_id=purchase_id,
        updated_at=old_updated_at,
    )
    promo = build_promo_code(id=21)
    session = RecordingSession(_ScalarResult(redemption), _ScalarResult(promo))

    result_redemption, result_promo, was_revoked = (
        await promo_repo_redemptions.revoke_redemption_for_refund(
            session,
            purchase_id=purchase_id,
            promo_code_id=21,
            now_utc=NOW_UTC,
        )
    )

    assert result_redemption is redemption
    assert result_promo is promo
    assert was_revoked is False
    assert redemption.status == "REVOKED"
    assert redemption.updated_at == old_updated_at
