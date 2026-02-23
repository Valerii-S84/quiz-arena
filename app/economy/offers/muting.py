from __future__ import annotations

from datetime import datetime

from app.db.models.offers_impressions import OfferImpression
from app.economy.offers.constants import (
    BLOCKING_MODAL_COOLDOWN,
    BLOCKING_OFFER_CODES,
    OFFER_MUTE_WINDOW,
    OFFER_NOT_SHOW_DISMISS_REASON,
    OFFER_REPEAT_COOLDOWN,
)


def is_offer_muted(
    *,
    offer_code: str,
    recent_impressions: list[OfferImpression],
    now_utc: datetime,
) -> bool:
    mute_threshold = now_utc - OFFER_MUTE_WINDOW
    for impression in recent_impressions:
        if impression.offer_code != offer_code:
            continue
        if impression.dismiss_reason != OFFER_NOT_SHOW_DISMISS_REASON:
            continue
        dismissed_at = impression.dismissed_at or impression.clicked_at
        if dismissed_at is None:
            continue
        if dismissed_at >= mute_threshold:
            return True
    return False


def was_offer_shown_recently(
    *,
    offer_code: str,
    recent_impressions: list[OfferImpression],
    now_utc: datetime,
) -> bool:
    repeat_threshold = now_utc - OFFER_REPEAT_COOLDOWN
    for impression in recent_impressions:
        if impression.offer_code == offer_code and impression.shown_at >= repeat_threshold:
            return True
    return False


def has_recent_blocking_modal(
    *,
    recent_impressions: list[OfferImpression],
    now_utc: datetime,
) -> bool:
    threshold = now_utc - BLOCKING_MODAL_COOLDOWN
    for impression in recent_impressions:
        if impression.offer_code in BLOCKING_OFFER_CODES and impression.shown_at >= threshold:
            return True
    return False
