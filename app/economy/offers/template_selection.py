from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.offers_repo import OffersRepo
from app.economy.offers.constants import (
    MONETIZATION_IMPRESSIONS_PER_DAY_CAP,
    OFFER_MUTE_WINDOW,
    OFFER_TEMPLATES,
    TRIGGER_RESOLUTION_ORDER,
)
from app.economy.offers.muting import (
    has_recent_blocking_modal,
    is_offer_muted,
    was_offer_shown_recently,
)
from app.economy.offers.time_utils import berlin_now
from app.economy.offers.types import OfferTemplate


async def select_template_with_caps(
    session: AsyncSession,
    *,
    user_id: int,
    trigger_codes: set[str],
    now_utc: datetime,
) -> OfferTemplate | None:
    if not trigger_codes:
        return None

    berlin_today = berlin_now(now_utc).date()
    recent_impressions = await OffersRepo.list_for_user_since(
        session,
        user_id=user_id,
        shown_since_utc=now_utc - OFFER_MUTE_WINDOW,
    )

    daily_impressions = sum(
        1 for impression in recent_impressions if impression.local_date_berlin == berlin_today
    )
    if daily_impressions >= MONETIZATION_IMPRESSIONS_PER_DAY_CAP:
        return None

    blocking_recently_shown = has_recent_blocking_modal(
        recent_impressions=recent_impressions,
        now_utc=now_utc,
    )

    order_map = {trigger_code: index for index, trigger_code in enumerate(TRIGGER_RESOLUTION_ORDER)}
    ordered_templates = sorted(
        (OFFER_TEMPLATES[trigger_code] for trigger_code in trigger_codes),
        key=lambda template: (
            -template.priority,
            order_map.get(template.trigger_code, len(order_map)),
        ),
    )

    for template in ordered_templates:
        if template.blocking_modal and blocking_recently_shown:
            continue
        if was_offer_shown_recently(
            offer_code=template.offer_code,
            recent_impressions=recent_impressions,
            now_utc=now_utc,
        ):
            continue
        if is_offer_muted(
            offer_code=template.offer_code,
            recent_impressions=recent_impressions,
            now_utc=now_utc,
        ):
            continue
        return template

    return None
