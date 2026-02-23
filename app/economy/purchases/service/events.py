from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_SYSTEM, emit_analytics_event
from app.db.models.purchases import Purchase


async def _emit_purchase_event(
    session: AsyncSession,
    *,
    event_type: str,
    purchase: Purchase,
    happened_at: datetime,
    extra_payload: dict[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "purchase_id": str(purchase.id),
        "product_code": purchase.product_code,
        "product_type": purchase.product_type,
        "status": purchase.status,
        "stars_amount": purchase.stars_amount,
        "discount_stars_amount": purchase.discount_stars_amount,
    }
    if extra_payload:
        payload.update(extra_payload)
    await emit_analytics_event(
        session,
        event_type=event_type,
        source=EVENT_SOURCE_SYSTEM,
        user_id=purchase.user_id,
        payload=payload,
        happened_at=happened_at,
    )
