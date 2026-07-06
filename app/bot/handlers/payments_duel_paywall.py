from __future__ import annotations

from datetime import datetime
from typing import Any

from app.game.arena_duels.analytics import (
    ARENA_EVENT_DUEL_TICKET_CLICKED,
    ARENA_EVENT_PREMIUM_WEEK_CLICKED,
    ARENA_PAYWALL_CONTEXTS,
    build_arena_event_payload,
    emit_arena_analytics_event,
    with_paywall_context,
)
from app.game.duels.constants import (
    DUEL_PAYWALL_CALLBACK_CONTEXT,
    DUEL_PREMIUM_WEEK_PRODUCT_CODE,
    DUEL_TICKET_PRODUCT_CODE,
)


async def _emit_duel_paywall_click(
    session: Any,
    *,
    user_id: int,
    product_code: str,
    happened_at: datetime,
    paywall_context: str | None = None,
) -> None:
    event_type = _duel_paywall_click_event_type(product_code)
    if event_type is None:
        return
    await emit_arena_analytics_event(
        session,
        event_type=event_type,
        happened_at=happened_at,
        user_id=user_id,
        payload=with_paywall_context(
            build_arena_event_payload(
                user_id=user_id,
                action="buy",
                access_type=product_code,
            ),
            paywall_context,
        ),
    )


def _duel_paywall_click_event_type(product_code: str) -> str | None:
    if product_code == DUEL_TICKET_PRODUCT_CODE:
        return ARENA_EVENT_DUEL_TICKET_CLICKED
    if product_code == DUEL_PREMIUM_WEEK_PRODUCT_CODE:
        return ARENA_EVENT_PREMIUM_WEEK_CLICKED
    return None


def _is_duel_paywall_callback(callback_data: str, *, product_code: str) -> bool:
    parts = callback_data.split(":")
    return (
        len(parts) in {3, 4}
        and parts[0] == "buy"
        and parts[1] == product_code
        and parts[2] == DUEL_PAYWALL_CALLBACK_CONTEXT
        and (len(parts) == 3 or parts[3] in ARENA_PAYWALL_CONTEXTS)
        and _duel_paywall_click_event_type(product_code) is not None
    )


def _duel_paywall_context_from_callback(callback_data: str, *, product_code: str) -> str | None:
    if not _is_duel_paywall_callback(callback_data, product_code=product_code):
        return None
    parts = callback_data.split(":")
    if len(parts) == 4:
        return parts[3]
    return None
