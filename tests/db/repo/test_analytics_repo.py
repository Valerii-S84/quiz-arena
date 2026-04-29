from __future__ import annotations

from datetime import date, datetime, timezone

from app.db.models.analytics_daily import AnalyticsDaily
from app.db.repo.analytics_aggregations import (
    count_applied_promo_redemptions_between,
    count_credited_purchases_between,
    count_distinct_active_users_between,
    count_distinct_credited_purchasers_between,
    count_events_by_type_between,
    count_promo_redemptions_between,
    count_promo_to_paid_conversions_between,
    count_quiz_sessions_completed_between,
    count_quiz_sessions_started_between,
)
from app.db.repo.analytics_models import AnalyticsDailyUpsert
from app.db.repo.analytics_mutations import (
    create_daily_cup_push_event_once,
    create_event,
    delete_events_created_before,
    upsert_daily,
)
from app.db.repo.analytics_queries import list_daily, list_user_ids_by_event_type_and_tournament
from app.db.repo.analytics_repo import AnalyticsRepo
from tests.db.repo._helpers import IterableScalarsResult, RecordingSession, compile_statement
from tests.type_helpers import RowsResult as _RowsResult
from tests.type_helpers import ScalarResult as _ScalarResult
from tests.type_helpers import ScalarsResult as _ScalarsResult

UTC = timezone.utc


def test_analytics_repo_facade_exposes_repo_functions() -> None:
    assert AnalyticsRepo.create_event is create_event
    assert AnalyticsRepo.upsert_daily is upsert_daily
    assert AnalyticsRepo.list_daily is list_daily
    assert AnalyticsRepo.count_events_by_type_between is count_events_by_type_between


def _daily_upsert() -> AnalyticsDailyUpsert:
    return AnalyticsDailyUpsert(
        local_date_berlin=date(2026, 3, 14),
        dau=10,
        wau=20,
        mau=30,
        purchases_credited_total=4,
        purchasers_total=3,
        purchase_rate=0.3,
        promo_redemptions_total=5,
        promo_redemptions_applied_total=4,
        promo_redemption_rate=0.8,
        promo_to_paid_conversions_total=2,
        quiz_sessions_started_total=100,
        quiz_sessions_completed_total=80,
        gameplay_completion_rate=0.8,
        energy_zero_events_total=7,
        streak_lost_events_total=1,
        referral_reward_milestone_events_total=2,
        referral_reward_granted_events_total=1,
        purchase_init_events_total=9,
        purchase_invoice_sent_events_total=8,
        purchase_precheckout_ok_events_total=7,
        purchase_paid_uncredited_events_total=6,
        purchase_credited_events_total=5,
        calculated_at=datetime(2026, 3, 14, 12, 0, tzinfo=UTC),
    )


async def test_analytics_mutations_create_unique_upsert_and_delete_events() -> None:
    happened_at = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)

    create_session = RecordingSession()
    event = await create_event(
        create_session,
        event_type="quiz.started",
        source="BOT",
        user_id=7,
        local_date_berlin=date(2026, 3, 14),
        payload={"mode": "daily"},
        happened_at=happened_at,
    )
    assert event.event_type == "quiz.started"
    assert create_session.added == [event]
    assert create_session.flushed is True

    unique_session = RecordingSession(_ScalarResult(10))
    assert (
        await create_daily_cup_push_event_once(
            unique_session,
            event_type="daily_cup.turn_reminder_sent",
            source="WORKER",
            user_id=7,
            local_date_berlin=date(2026, 3, 14),
            payload={"tournament_id": "daily-1"},
            happened_at=happened_at,
        )
        is True
    )

    upsert_session = RecordingSession(_RowsResult([]))
    await upsert_daily(upsert_session, row=_daily_upsert())
    upsert_sql = compile_statement(upsert_session.statement)
    assert "INSERT INTO analytics_daily" in upsert_sql
    assert "ON CONFLICT (local_date_berlin) DO UPDATE" in upsert_sql

    delete_session = RecordingSession(IterableScalarsResult([1, 2]))
    assert (
        await delete_events_created_before(
            delete_session,
            cutoff_utc=happened_at,
            limit=0,
        )
        == 2
    )
    assert "LIMIT 1" in compile_statement(delete_session.statement)


async def test_analytics_queries_list_daily_and_tournament_event_users() -> None:
    daily = AnalyticsDaily(local_date_berlin=date(2026, 3, 14), calculated_at=datetime.now(UTC))
    list_session = RecordingSession(_ScalarsResult([daily]))
    assert await list_daily(list_session, limit=7) == [daily]
    assert "ORDER BY analytics_daily.local_date_berlin DESC" in compile_statement(
        list_session.statement
    )

    empty_session = RecordingSession()
    assert (
        await list_user_ids_by_event_type_and_tournament(
            empty_session,
            event_type="daily_cup.joined",
            tournament_id="daily-1",
            user_ids=[],
        )
        == set()
    )

    user_session = RecordingSession(_ScalarsResult([7, None, 8]))
    assert await list_user_ids_by_event_type_and_tournament(
        user_session,
        event_type="daily_cup.joined",
        tournament_id="daily-1",
        user_ids=[7, 8, 9],
    ) == {7, 8}


async def test_analytics_count_aggregations_apply_time_windows() -> None:
    from_utc = datetime(2026, 3, 14, 0, 0, tzinfo=UTC)
    to_utc = datetime(2026, 3, 15, 0, 0, tzinfo=UTC)
    count_functions = (
        count_distinct_active_users_between,
        count_credited_purchases_between,
        count_distinct_credited_purchasers_between,
        count_promo_to_paid_conversions_between,
        count_promo_redemptions_between,
        count_applied_promo_redemptions_between,
        count_quiz_sessions_started_between,
        count_quiz_sessions_completed_between,
    )

    for index, count_function in enumerate(count_functions, start=1):
        session = RecordingSession(_ScalarResult(index))
        assert await count_function(session, from_utc=from_utc, to_utc=to_utc) == index
        sql = compile_statement(session.statement)
        assert ">=" in sql
        assert "<" in sql

    empty_session = RecordingSession()
    assert (
        await count_events_by_type_between(
            empty_session,
            from_utc=from_utc,
            to_utc=to_utc,
            event_types=(),
        )
        == {}
    )

    events_session = RecordingSession(_RowsResult([("quiz.started", 3), ("quiz.completed", 2)]))
    assert await count_events_by_type_between(
        events_session,
        from_utc=from_utc,
        to_utc=to_utc,
        event_types=("quiz.started", "quiz.completed"),
    ) == {"quiz.started": 3, "quiz.completed": 2}
