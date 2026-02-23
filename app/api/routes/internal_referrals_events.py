from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from app.db.repo.outbox_events_repo import OutboxEventsRepo
from app.db.session import SessionLocal

from .internal_referrals_constants import REFERRAL_NOTIFICATION_EVENT_TYPES
from .internal_referrals_helpers import _assert_internal_access
from .internal_referrals_models import (
    ReferralNotificationEventResponse,
    ReferralNotificationsFeedResponse,
)


def _normalize_event_type(raw_event_type: str | None) -> str | None:
    if raw_event_type is None:
        return None
    return raw_event_type.strip()


async def get_referrals_notification_events(
    *,
    request: Request,
    window_hours: int,
    event_type: str | None,
    limit: int,
) -> ReferralNotificationsFeedResponse:
    _assert_internal_access(request)
    now_utc = datetime.now(timezone.utc)
    since_utc = now_utc - timedelta(hours=window_hours)

    normalized_type: str | None = None
    event_types: tuple[str, ...] = tuple(sorted(REFERRAL_NOTIFICATION_EVENT_TYPES))
    if event_type is not None:
        normalized_type = _normalize_event_type(event_type)
        if normalized_type not in REFERRAL_NOTIFICATION_EVENT_TYPES:
            raise HTTPException(status_code=422, detail={"code": "E_REFERRAL_EVENT_TYPE_INVALID"})
        event_types = (normalized_type,)

    async with SessionLocal.begin() as session:
        events = await OutboxEventsRepo.list_events_since(
            session,
            since_utc=since_utc,
            event_types=event_types,
            limit=limit,
        )
        by_type = await OutboxEventsRepo.count_by_type_since(
            session,
            since_utc=since_utc,
            event_types=event_types,
        )
        by_status = await OutboxEventsRepo.count_by_status_since(
            session,
            since_utc=since_utc,
            event_types=event_types,
        )

    return ReferralNotificationsFeedResponse(
        generated_at=now_utc,
        window_hours=window_hours,
        event_type_filter=normalized_type,
        total_events=sum(by_type.values()),
        by_type=by_type,
        by_status=by_status,
        events=[
            ReferralNotificationEventResponse(
                id=int(item.id),
                event_type=str(item.event_type),
                status=str(item.status),
                created_at=item.created_at,
                payload=item.payload,
            )
            for item in events
        ],
    )
