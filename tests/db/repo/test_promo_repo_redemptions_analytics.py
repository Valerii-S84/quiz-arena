from __future__ import annotations

from datetime import datetime, timezone

from app.db.repo import promo_repo_redemptions_analytics
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult

UTC = timezone.utc


async def test_count_redemptions_by_status_groups_recent_redemptions() -> None:
    since_utc = datetime(2026, 3, 1, tzinfo=UTC)
    session = RecordingSession(_RowsResult([("APPLIED", 8), ("REVOKED", 1)]))

    rows = await promo_repo_redemptions_analytics.count_redemptions_by_status(
        session,
        since_utc=since_utc,
    )

    assert rows == {"APPLIED": 8, "REVOKED": 1}
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "promo_redemptions.created_at >=" in sql
    assert "GROUP BY promo_redemptions.status" in sql


async def test_count_discount_redemptions_by_status_filters_percent_discount_codes() -> None:
    since_utc = datetime(2026, 3, 1, tzinfo=UTC)
    session = RecordingSession(_RowsResult([("APPLIED", 3), ("REJECTED", 2)]))

    rows = await promo_repo_redemptions_analytics.count_discount_redemptions_by_status(
        session,
        since_utc=since_utc,
    )

    assert rows == {"APPLIED": 3, "REJECTED": 2}
    assert session.statement is not None
    sql = compile_statement(session.statement)
    assert "JOIN promo_codes ON promo_codes.id = promo_redemptions.promo_code_id" in sql
    assert "promo_codes.promo_type = 'PERCENT_DISCOUNT'" in sql
    assert "GROUP BY promo_redemptions.status" in sql
