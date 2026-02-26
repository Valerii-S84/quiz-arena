from __future__ import annotations

from app.db.repo.referrals_aggregations import (  # noqa: F401
    count_by_status_since,
    count_for_referrer,
    count_qualified_for_referrer,
    count_referrer_starts_between,
    count_rewarded_for_referrer,
    count_rewards_for_referrer_between,
    count_started_since,
    list_recent_fraud_cases_since,
    list_referrer_stats_since,
)
from app.db.repo.referrals_mutations import create, mark_started_as_rejected_fraud  # noqa: F401
from app.db.repo.referrals_queries import (  # noqa: F401
    get_by_id_for_update,
    get_by_referred_user_id,
    get_reverse_pair_since,
    list_for_referrer,
    list_for_referrer_for_update,
    list_for_referrers_for_update,
    list_for_review_since,
    list_referrer_ids_with_reward_candidates,
    list_referrer_ids_with_reward_notifications,
    list_started_ids,
)


class ReferralsRepo:
    get_by_referred_user_id = staticmethod(get_by_referred_user_id)
    get_reverse_pair_since = staticmethod(get_reverse_pair_since)
    count_referrer_starts_between = staticmethod(count_referrer_starts_between)
    create = staticmethod(create)
    list_started_ids = staticmethod(list_started_ids)
    get_by_id_for_update = staticmethod(get_by_id_for_update)
    list_referrer_ids_with_reward_candidates = staticmethod(
        list_referrer_ids_with_reward_candidates
    )
    list_referrer_ids_with_reward_notifications = staticmethod(
        list_referrer_ids_with_reward_notifications
    )
    list_for_referrer_for_update = staticmethod(list_for_referrer_for_update)
    list_for_referrers_for_update = staticmethod(list_for_referrers_for_update)
    list_for_referrer = staticmethod(list_for_referrer)
    count_rewards_for_referrer_between = staticmethod(count_rewards_for_referrer_between)
    count_qualified_for_referrer = staticmethod(count_qualified_for_referrer)
    count_rewarded_for_referrer = staticmethod(count_rewarded_for_referrer)
    count_for_referrer = staticmethod(count_for_referrer)
    mark_started_as_rejected_fraud = staticmethod(mark_started_as_rejected_fraud)
    count_started_since = staticmethod(count_started_since)
    count_by_status_since = staticmethod(count_by_status_since)
    list_referrer_stats_since = staticmethod(list_referrer_stats_since)
    list_recent_fraud_cases_since = staticmethod(list_recent_fraud_cases_since)
    list_for_review_since = staticmethod(list_for_review_since)


__all__ = ["ReferralsRepo"]
