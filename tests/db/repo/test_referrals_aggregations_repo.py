from __future__ import annotations

from datetime import datetime, timezone

from app.db.repo.referrals_repo import ReferralsRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult as _ScalarResult

UTC = timezone.utc


async def test_referrer_start_count_filters_created_window() -> None:
    session = RecordingSession(_ScalarResult(4))

    count = await ReferralsRepo.count_referrer_starts_between(
        session,
        referrer_user_id=7,
        from_utc=datetime(2026, 3, 1, tzinfo=UTC),
        to_utc=datetime(2026, 4, 1, tzinfo=UTC),
    )

    assert count == 4
    sql = compile_statement(session.statement)
    assert "referrals.referrer_user_id = 7" in sql
    assert "referrals.created_at >=" in sql
    assert "referrals.created_at <" in sql


async def test_referrer_status_counts_apply_expected_status_filters() -> None:
    qualified_session = RecordingSession(_ScalarResult(3))
    assert (
        await ReferralsRepo.count_qualified_for_referrer(
            qualified_session,
            referrer_user_id=7,
        )
        == 3
    )
    qualified_sql = compile_statement(qualified_session.statement)
    assert "referrals.status IN ('QUALIFIED', 'DEFERRED_LIMIT', 'REWARDED')" in qualified_sql

    rewarded_session = RecordingSession(_ScalarResult(None))
    assert (
        await ReferralsRepo.count_rewarded_for_referrer(
            rewarded_session,
            referrer_user_id=7,
        )
        == 0
    )
    assert "referrals.status = 'REWARDED'" in compile_statement(rewarded_session.statement)

    total_session = RecordingSession(_ScalarResult(9))
    assert await ReferralsRepo.count_for_referrer(total_session, referrer_user_id=7) == 9
    assert "referrals.referrer_user_id = 7" in compile_statement(total_session.statement)


async def test_started_since_count_filters_created_at() -> None:
    session = RecordingSession(_ScalarResult(6))

    assert (
        await ReferralsRepo.count_started_since(
            session,
            since_utc=datetime(2026, 3, 1, tzinfo=UTC),
        )
        == 6
    )
    assert "referrals.created_at >=" in compile_statement(session.statement)
