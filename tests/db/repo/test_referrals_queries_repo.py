from __future__ import annotations

from datetime import datetime, timezone

from app.db.models.referrals import Referral
from app.db.repo.referrals_repo import ReferralsRepo
from tests.db.repo._helpers import RecordingSession, compile_statement
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


def _referral(**overrides: object) -> Referral:
    payload: dict[str, object] = {
        "id": 11,
        "referrer_user_id": 7,
        "referred_user_id": 8,
        "referral_code": "REF7",
        "status": "QUALIFIED",
        "qualified_at": datetime(2026, 3, 14, 12, 0, tzinfo=UTC),
        "rewarded_at": None,
        "notified_at": None,
        "fraud_score": 0,
        "created_at": datetime(2026, 3, 14, 10, 0, tzinfo=UTC),
    }
    payload.update(overrides)
    return Referral(**payload)


async def test_referral_lookup_queries_filter_referred_and_reverse_pair() -> None:
    since_utc = datetime(2026, 3, 1, tzinfo=UTC)
    referral = _referral()

    referred_session = RecordingSession(_ScalarResult(referral))
    assert (
        await ReferralsRepo.get_by_referred_user_id(
            referred_session,
            referred_user_id=8,
        )
        is referral
    )
    assert "referrals.referred_user_id = 8" in compile_statement(referred_session.statement)

    reverse_session = RecordingSession(_ScalarResult(None))
    assert (
        await ReferralsRepo.get_reverse_pair_since(
            reverse_session,
            referrer_user_id=7,
            referred_user_id=8,
            since_utc=since_utc,
        )
        is None
    )
    reverse_sql = compile_statement(reverse_session.statement)
    assert "referrals.referrer_user_id = 8" in reverse_sql
    assert "referrals.referred_user_id = 7" in reverse_sql
    assert "referrals.created_at >=" in reverse_sql


async def test_started_and_id_lock_queries_apply_ordering_and_for_update() -> None:
    started_session = RecordingSession(_ScalarsResult([11, 12]))

    assert await ReferralsRepo.list_started_ids(started_session, limit=25) == [11, 12]
    started_sql = compile_statement(started_session.statement)
    assert "referrals.status = 'STARTED'" in started_sql
    assert "ORDER BY referrals.created_at ASC" in started_sql
    assert "LIMIT 25" in started_sql

    lock_session = RecordingSession(_ScalarResult(None))
    await ReferralsRepo.get_by_id_for_update(lock_session, referral_id=11)
    lock_sql = compile_statement(lock_session.statement)
    assert "referrals.id = 11" in lock_sql
    assert "FOR UPDATE" in lock_sql


async def test_reward_candidate_query_requires_qualified_and_paid_referrer() -> None:
    session = RecordingSession(_ScalarsResult(["7", "8"]))

    rows = await ReferralsRepo.list_referrer_ids_with_reward_candidates(
        session,
        qualified_before_utc=datetime(2026, 3, 15, tzinfo=UTC),
        limit=50,
    )

    assert rows == [7, 8]
    sql = compile_statement(session.statement)
    assert "referrals.status IN ('QUALIFIED', 'DEFERRED_LIMIT')" in sql
    assert "referrals.qualified_at IS NOT NULL" in sql
    assert "EXISTS (SELECT purchases.id" in sql
    assert "purchases.user_id = referrals.referrer_user_id" in sql
    assert "purchases.paid_at IS NOT NULL" in sql
    assert "purchases.stars_amount > 0" in sql
    assert "GROUP BY referrals.referrer_user_id" in sql
    assert "LIMIT 50" in sql


async def test_referrer_reward_review_queries_filter_statuses_and_group_rows() -> None:
    first = _referral(id=11, referrer_user_id=7)
    second = _referral(id=12, referrer_user_id=7, status="DEFERRED_LIMIT")
    third = _referral(id=13, referrer_user_id=8, status="REWARDED")

    one_session = RecordingSession(_ScalarsResult([first, second]))
    assert await ReferralsRepo.list_for_referrer_for_update(
        one_session,
        referrer_user_id=7,
    ) == [first, second]
    one_sql = compile_statement(one_session.statement)
    assert "referrals.referrer_user_id = 7" in one_sql
    assert "referrals.status IN" in one_sql
    assert "ORDER BY referrals.qualified_at ASC NULLS LAST" in one_sql
    assert "FOR UPDATE" in one_sql

    grouped_session = RecordingSession(_ScalarsResult([first, second, third]))
    grouped = await ReferralsRepo.list_for_referrers_for_update(
        grouped_session,
        referrer_user_ids=[8, 7, 7],
    )
    assert grouped == {7: [first, second], 8: [third]}
    grouped_sql = compile_statement(grouped_session.statement)
    assert "referrals.referrer_user_id IN" in grouped_sql
    assert "referrals.referrer_user_id ASC" in grouped_sql
    assert "FOR UPDATE" in grouped_sql

    plain_session = RecordingSession(_ScalarsResult([first, second]))
    assert await ReferralsRepo.list_for_referrer(
        plain_session,
        referrer_user_id=7,
    ) == [first, second]
    plain_sql = compile_statement(plain_session.statement)
    assert "referrals.referrer_user_id = 7" in plain_sql
    assert "ORDER BY referrals.qualified_at ASC NULLS LAST" in plain_sql
    assert "FOR UPDATE" not in plain_sql

    empty_session = RecordingSession()
    assert (
        await ReferralsRepo.list_for_referrers_for_update(
            empty_session,
            referrer_user_ids=[],
        )
        == {}
    )
    assert empty_session.statements == []


async def test_review_and_notification_queries_apply_optional_filters() -> None:
    since_utc = datetime(2026, 3, 1, tzinfo=UTC)
    notified_at = datetime(2026, 3, 16, tzinfo=UTC)
    referral = _referral(status="REJECTED_FRAUD")

    review_session = RecordingSession(_ScalarsResult([referral]))
    assert await ReferralsRepo.list_for_review_since(
        review_session,
        since_utc=since_utc,
        status="REJECTED_FRAUD",
        limit=20,
    ) == [referral]
    review_sql = compile_statement(review_session.statement)
    assert "referrals.created_at >=" in review_sql
    assert "referrals.status = 'REJECTED_FRAUD'" in review_sql
    assert "ORDER BY referrals.fraud_score DESC" in review_sql
    assert "LIMIT 20" in review_sql

    unfiltered_review_session = RecordingSession(_ScalarsResult([referral]))
    assert await ReferralsRepo.list_for_review_since(
        unfiltered_review_session,
        since_utc=since_utc,
        limit=10,
    ) == [referral]
    unfiltered_sql = compile_statement(unfiltered_review_session.statement)
    assert "referrals.created_at >=" in unfiltered_sql
    assert "referrals.status =" not in unfiltered_sql

    notification_session = RecordingSession(_ScalarsResult(["7", "8"]))
    rows = await ReferralsRepo.list_referrer_ids_with_reward_notifications(
        notification_session,
        notified_at=notified_at,
    )
    assert rows == [7, 8]
    notification_sql = compile_statement(notification_session.statement)
    assert "referrals.notified_at =" in notification_sql
    assert "GROUP BY referrals.referrer_user_id" in notification_sql
    assert "ORDER BY referrals.referrer_user_id ASC" in notification_sql
