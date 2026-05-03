from __future__ import annotations

from app.db.repo.analytics_aggregations import (  # noqa: F401
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
from app.db.repo.analytics_models import AnalyticsDailyUpsert  # noqa: F401
from app.db.repo.analytics_mutations import (  # noqa: F401
    create_arena_beaten_notification_event_once,
    create_arena_revanche_event_once,
    create_daily_cup_push_event_once,
    create_event,
    delete_arena_revanche_events,
    delete_events_created_before,
    lock_arena_beaten_notification_event_key,
    lock_arena_revanche_event_key,
    lock_arena_revanche_sender_quota,
    upsert_daily,
)
from app.db.repo.analytics_queries import (  # noqa: F401
    count_user_events_by_payload_value,
    count_user_events_since,
    count_user_events_since_by_payload_value,
    get_arena_revanche_event_payload,
    has_arena_beaten_notification_event,
    has_arena_revanche_event,
    list_daily,
    list_user_ids_by_event_type_and_tournament,
)


class AnalyticsRepo:
    create_event = staticmethod(create_event)
    create_daily_cup_push_event_once = staticmethod(create_daily_cup_push_event_once)
    create_arena_beaten_notification_event_once = staticmethod(
        create_arena_beaten_notification_event_once
    )
    create_arena_revanche_event_once = staticmethod(create_arena_revanche_event_once)
    delete_arena_revanche_events = staticmethod(delete_arena_revanche_events)
    lock_arena_beaten_notification_event_key = staticmethod(
        lock_arena_beaten_notification_event_key
    )
    lock_arena_revanche_event_key = staticmethod(lock_arena_revanche_event_key)
    lock_arena_revanche_sender_quota = staticmethod(lock_arena_revanche_sender_quota)
    has_arena_beaten_notification_event = staticmethod(has_arena_beaten_notification_event)
    has_arena_revanche_event = staticmethod(has_arena_revanche_event)
    get_arena_revanche_event_payload = staticmethod(get_arena_revanche_event_payload)
    count_user_events_by_payload_value = staticmethod(count_user_events_by_payload_value)
    count_user_events_since = staticmethod(count_user_events_since)
    count_user_events_since_by_payload_value = staticmethod(
        count_user_events_since_by_payload_value
    )
    count_distinct_active_users_between = staticmethod(count_distinct_active_users_between)
    count_credited_purchases_between = staticmethod(count_credited_purchases_between)
    count_distinct_credited_purchasers_between = staticmethod(
        count_distinct_credited_purchasers_between
    )
    count_promo_to_paid_conversions_between = staticmethod(count_promo_to_paid_conversions_between)
    count_promo_redemptions_between = staticmethod(count_promo_redemptions_between)
    count_applied_promo_redemptions_between = staticmethod(count_applied_promo_redemptions_between)
    count_quiz_sessions_started_between = staticmethod(count_quiz_sessions_started_between)
    count_quiz_sessions_completed_between = staticmethod(count_quiz_sessions_completed_between)
    count_events_by_type_between = staticmethod(count_events_by_type_between)
    upsert_daily = staticmethod(upsert_daily)
    list_daily = staticmethod(list_daily)
    list_user_ids_by_event_type_and_tournament = staticmethod(
        list_user_ids_by_event_type_and_tournament
    )
    delete_events_created_before = staticmethod(delete_events_created_before)


__all__ = ["AnalyticsDailyUpsert", "AnalyticsRepo"]
