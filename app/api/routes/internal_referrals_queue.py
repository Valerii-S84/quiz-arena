from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request

from app.db.repo.referrals_repo import ReferralsRepo
from app.db.session import SessionLocal

from .internal_referrals_constants import REFERRAL_REVIEW_STATUSES
from .internal_referrals_helpers import _as_review_case, _assert_internal_access
from .internal_referrals_models import ReferralReviewQueueResponse


def _normalize_status(raw_status: str | None) -> str | None:
    if raw_status is None:
        return None
    return raw_status.strip().upper()


async def get_referrals_review_queue(
    *,
    request: Request,
    window_hours: int,
    status: str | None,
    limit: int,
) -> ReferralReviewQueueResponse:
    _assert_internal_access(request)
    now_utc = datetime.now(timezone.utc)
    status_filter: str | None = None
    if status is not None:
        normalized_status = _normalize_status(status)
        if normalized_status not in REFERRAL_REVIEW_STATUSES:
            raise HTTPException(status_code=422, detail={"code": "E_REFERRAL_STATUS_INVALID"})
        status_filter = normalized_status

    since_utc = now_utc - timedelta(hours=window_hours)
    async with SessionLocal.begin() as session:
        referrals = await ReferralsRepo.list_for_review_since(
            session,
            since_utc=since_utc,
            status=status_filter,
            limit=limit,
        )

    return ReferralReviewQueueResponse(
        generated_at=now_utc,
        window_hours=window_hours,
        status_filter=status_filter,
        cases=[_as_review_case(referral) for referral in referrals],
    )
