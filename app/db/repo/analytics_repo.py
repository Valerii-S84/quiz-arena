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
    create_event,
    delete_events_created_before,
    upsert_daily,
)
from app.db.repo.analytics_queries import list_daily  # noqa: F401


class AnalyticsRepo:
    create_event = staticmethod(create_event)
    count_distinct_active_users_between = staticmethod(count_distinct_active_users_between)
    count_credited_purchases_between = staticmethod(count_credited_purchases_between)
    count_distinct_credited_purchasers_between = staticmethod(
        count_distinct_credited_purchasers_between
    )
    count_promo_to_paid_conversions_between = staticmethod(count_promo_to_paid_conversions_between)
    count_promo_redemptions_between = staticmethod(count_promo_redemptions_between)
    count_applied_promo_redemptions_between = staticmethod(
        count_applied_promo_redemptions_between
    )
    count_quiz_sessions_started_between = staticmethod(count_quiz_sessions_started_between)
    count_quiz_sessions_completed_between = staticmethod(count_quiz_sessions_completed_between)
    count_events_by_type_between = staticmethod(count_events_by_type_between)
    upsert_daily = staticmethod(upsert_daily)
    list_daily = staticmethod(list_daily)
    delete_events_created_before = staticmethod(delete_events_created_before)


__all__ = ["AnalyticsDailyUpsert", "AnalyticsRepo"]
