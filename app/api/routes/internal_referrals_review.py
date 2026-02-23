from __future__ import annotations

from decimal import Decimal

import structlog
from fastapi import HTTPException, Request

from app.db.repo.referrals_repo import ReferralsRepo
from app.db.session import SessionLocal
from app.economy.referrals.constants import FRAUD_SCORE_VELOCITY

from .internal_referrals_constants import REFERRAL_REVIEW_DECISIONS, REFERRAL_REVIEW_STATUSES
from .internal_referrals_helpers import _as_review_case, _assert_internal_access
from .internal_referrals_models import ReferralReviewActionRequest, ReferralReviewActionResponse

logger = structlog.get_logger(__name__)


def _resolve_next_status(*, current_status: str, decision: str) -> str | None:
    if decision == "CONFIRM_FRAUD":
        if current_status in {"STARTED", "REJECTED_FRAUD"}:
            return "REJECTED_FRAUD"
        return None
    if decision == "REOPEN":
        if current_status in {"REJECTED_FRAUD", "CANCELED", "STARTED"}:
            return "STARTED"
        return None
    if decision == "CANCEL":
        if current_status in {"STARTED", "REJECTED_FRAUD", "CANCELED"}:
            return "CANCELED"
        return None
    return None


async def apply_referral_review_decision(
    *,
    referral_id: int,
    payload: ReferralReviewActionRequest,
    request: Request,
) -> ReferralReviewActionResponse:
    _assert_internal_access(request)
    decision = payload.decision.strip().upper()
    if decision not in REFERRAL_REVIEW_DECISIONS:
        raise HTTPException(status_code=422, detail={"code": "E_REFERRAL_REVIEW_DECISION_INVALID"})

    expected_status: str | None = None
    if payload.expected_current_status is not None:
        expected_status = payload.expected_current_status.strip().upper()
        if expected_status not in REFERRAL_REVIEW_STATUSES:
            raise HTTPException(status_code=422, detail={"code": "E_REFERRAL_STATUS_INVALID"})

    idempotent_replay = True
    async with SessionLocal.begin() as session:
        referral = await ReferralsRepo.get_by_id_for_update(session, referral_id=referral_id)
        if referral is None:
            raise HTTPException(status_code=404, detail={"code": "E_REFERRAL_NOT_FOUND"})
        if expected_status is not None and referral.status != expected_status:
            raise HTTPException(status_code=409, detail={"code": "E_REFERRAL_STATUS_CONFLICT"})

        next_status = _resolve_next_status(current_status=referral.status, decision=decision)
        if next_status is None:
            raise HTTPException(
                status_code=409, detail={"code": "E_REFERRAL_REVIEW_DECISION_CONFLICT"}
            )

        previous_status = referral.status
        if referral.status != next_status:
            referral.status = next_status
            idempotent_replay = False

        if next_status == "REJECTED_FRAUD":
            if referral.fraud_score < FRAUD_SCORE_VELOCITY:
                referral.fraud_score = Decimal(FRAUD_SCORE_VELOCITY)
                idempotent_replay = False
        if next_status == "STARTED" and referral.fraud_score != Decimal("0"):
            referral.fraud_score = Decimal("0")
            idempotent_replay = False

        if next_status in {"REJECTED_FRAUD", "STARTED", "CANCELED"}:
            if referral.qualified_at is not None:
                referral.qualified_at = None
                idempotent_replay = False
            if referral.rewarded_at is not None:
                referral.rewarded_at = None
                idempotent_replay = False

        if not idempotent_replay:
            logger.info(
                "internal_referral_review_decision_applied",
                referral_id=referral.id,
                previous_status=previous_status,
                next_status=referral.status,
                decision=decision,
                reason=(payload.reason or "").strip() or None,
            )

        response = ReferralReviewActionResponse(
            referral=_as_review_case(referral),
            idempotent_replay=idempotent_replay,
        )
    return response
