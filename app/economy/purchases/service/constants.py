from __future__ import annotations

from datetime import timedelta

from app.economy.promo.constants import PROMO_DISCOUNT_RESERVATION_TTL

PROMO_RESERVATION_TTL = PROMO_DISCOUNT_RESERVATION_TTL
STREAK_SAVER_PURCHASE_LOCK_WINDOW = timedelta(days=7)
PREMIUM_PLAN_RANKS: dict[str, int] = {
    "PREMIUM_3_DAYS": 1,
    "PREMIUM_WEEK": 2,
    "PREMIUM_MONTH": 3,
    "PREMIUM_SEASON": 4,
    "PREMIUM_YEAR": 5,
}
