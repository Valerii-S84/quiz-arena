from __future__ import annotations

from datetime import timedelta

PROMO_RESERVATION_TTL = timedelta(days=7)
STREAK_SAVER_PURCHASE_LOCK_WINDOW = timedelta(days=7)
PREMIUM_PLAN_RANKS: dict[str, int] = {
    "PREMIUM_STARTER": 1,
    "PREMIUM_MONTH": 2,
    "PREMIUM_SEASON": 3,
    "PREMIUM_YEAR": 4,
}
