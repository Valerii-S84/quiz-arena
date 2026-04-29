from __future__ import annotations

from datetime import datetime, timezone

from app.db.repo.referrals_repo import ReferralsRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult as _ScalarResult

UTC = timezone.utc


async def test_count_referrer_starts_between_filters_referrer_and_window() -> None:
    session = RecordingSession(_ScalarResult(None))
    from_utc = datetime(2026, 3, 1, tzinfo=UTC)
    to_utc = datetime(2026, 4, 1, tzinfo=UTC)

    count = await ReferralsRepo.count_referrer_starts_between(
        session,
        referrer_user_id=7,
        from_utc=from_utc,
        to_utc=to_utc,
    )

    assert count == 0
    sql = compile_statement(session.statement)
    assert "referrals.referrer_user_id = 7" in sql
    assert "referrals.created_at >=" in sql
    assert "referrals.created_at <" in sql


async def test_count_qualified_for_referrer_includes_reward_pipeline_statuses() -> None:
    session = RecordingSession(_ScalarResult(5))

    count = await ReferralsRepo.count_qualified_for_referrer(
        session,
        referrer_user_id=7,
    )

    assert count == 5
    sql = compile_statement(session.statement)
    assert "referrals.referrer_user_id = 7" in sql
    assert "referrals.status IN ('QUALIFIED', 'DEFERRED_LIMIT', 'REWARDED')" in sql


async def test_count_referrer_totals_filter_by_referrer_and_rewarded_status() -> None:
    rewarded_session = RecordingSession(_ScalarResult(2))
    total_session = RecordingSession(_ScalarResult(9))

    assert (
        await ReferralsRepo.count_rewarded_for_referrer(
            rewarded_session,
            referrer_user_id=7,
        )
        == 2
    )
    assert await ReferralsRepo.count_for_referrer(total_session, referrer_user_id=7) == 9

    rewarded_sql = compile_statement(rewarded_session.statement)
    assert "referrals.referrer_user_id = 7" in rewarded_sql
    assert "referrals.status = 'REWARDED'" in rewarded_sql
    assert "referrals.referrer_user_id = 7" in compile_statement(total_session.statement)


async def test_count_started_since_filters_created_at_floor() -> None:
    session = RecordingSession(_ScalarResult(12))

    count = await ReferralsRepo.count_started_since(
        session,
        since_utc=datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert count == 12
    assert "referrals.created_at >=" in compile_statement(session.statement)
