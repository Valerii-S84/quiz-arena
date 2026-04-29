from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.repo import promo_repo_admin_runtime_redemptions as runtime_redemptions
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult
from tests.type_helpers import build_promo_redemption

UTC = timezone.utc
NOW_UTC = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)


async def test_runtime_redemption_count_queries_filter_by_promo_id() -> None:
    count_session = RecordingSession(_ScalarResult(7))
    assert await runtime_redemptions.count_redemptions(count_session, promo_id=21) == 7
    assert count_session.statement is not None
    assert "promo_redemptions.promo_code_id = 21" in compile_statement(count_session.statement)

    status_session = RecordingSession(_RowsResult([("RESERVED", 3), ("APPLIED", 2)]))
    rows = await runtime_redemptions.count_redemptions_by_status(status_session, promo_id=21)

    assert rows == {"RESERVED": 3, "APPLIED": 2}
    assert status_session.statement is not None
    status_sql = compile_statement(status_session.statement)
    assert "promo_redemptions.promo_code_id = 21" in status_sql
    assert "GROUP BY promo_redemptions.status" in status_sql


async def test_runtime_redemption_active_reserved_and_recent_listing_queries() -> None:
    active_session = RecordingSession(_ScalarResult(4))
    assert (
        await runtime_redemptions.count_active_reserved_redemptions(
            active_session,
            promo_id=21,
            now_utc=NOW_UTC,
        )
        == 4
    )
    assert active_session.statement is not None
    active_sql = compile_statement(active_session.statement)
    assert "promo_redemptions.status = 'RESERVED'" in active_sql
    assert "promo_redemptions.reserved_until >" in active_sql

    redemption = build_promo_redemption(promo_code_id=21)
    recent_session = RecordingSession(_RowsResult([(redemption, "PREMIUM_30")]))
    rows = await runtime_redemptions.list_recent_redemptions(
        recent_session,
        promo_id=21,
        limit=0,
    )

    assert rows == [(redemption, "PREMIUM_30")]
    assert recent_session.statement is not None
    recent_sql = compile_statement(recent_session.statement)
    assert "LEFT OUTER JOIN purchases" in recent_sql
    assert "promo_redemptions.promo_code_id = 21" in recent_sql
    assert "ORDER BY promo_redemptions.updated_at DESC" in recent_sql
    assert "LIMIT 1" in recent_sql


async def test_runtime_redemption_listing_paginates_and_clamps_limit() -> None:
    redemption = build_promo_redemption(promo_code_id=21)
    session = RecordingSession(_ScalarsResult([redemption]))

    rows = await runtime_redemptions.list_redemptions(
        session,
        promo_id=21,
        page=3,
        limit=250,
    )

    assert rows == [redemption]
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "promo_redemptions.promo_code_id = 21" in sql
    assert "LIMIT 200" in sql
    assert "OFFSET 400" in sql


async def test_runtime_redemption_revoke_active_reserved_rows_mutates_each_row() -> None:
    reserved_until = NOW_UTC + timedelta(minutes=15)
    redemption = build_promo_redemption(
        promo_code_id=21,
        status="RESERVED",
        reserved_until=reserved_until,
        updated_at=NOW_UTC - timedelta(minutes=1),
    )
    session = RecordingSession(_ScalarsResult([redemption]))

    rows = await runtime_redemptions.revoke_active_reserved_redemptions(
        session,
        promo_id=21,
        now_utc=NOW_UTC,
    )

    assert rows == [redemption]
    assert redemption.status == "REVOKED"
    assert redemption.reserved_until == NOW_UTC
    assert redemption.updated_at == NOW_UTC
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "promo_redemptions.status = 'RESERVED'" in sql
    assert "FOR UPDATE" in sql
