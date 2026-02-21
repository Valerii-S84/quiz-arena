from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.db.models.referrals import Referral
from app.db.repo.outbox_events_repo import OutboxEventsRepo
from app.db.repo.referrals_repo import ReferralsRepo
from app.db.session import SessionLocal
from app.economy.referrals.constants import FRAUD_SCORE_VELOCITY
from app.services.internal_auth import (
    extract_client_ip,
    is_client_ip_allowed,
    is_internal_request_authenticated,
)
from app.services.referrals_observability import (
    build_referrals_dashboard_snapshot,
    evaluate_referrals_alert_state,
    get_referrals_alert_thresholds,
)

router = APIRouter(tags=["internal", "referrals"])
logger = structlog.get_logger(__name__)
REFERRAL_REVIEW_STATUSES = {
    "STARTED",
    "QUALIFIED",
    "REWARDED",
    "REJECTED_FRAUD",
    "CANCELED",
    "DEFERRED_LIMIT",
}
REFERRAL_REVIEW_DECISIONS = {"CONFIRM_FRAUD", "REOPEN", "CANCEL"}
REFERRAL_NOTIFICATION_EVENT_TYPES = {
    "referral_reward_milestone_available",
    "referral_reward_granted",
}


class ReferralTopReferrerStatsResponse(BaseModel):
    referrer_user_id: int = Field(gt=0)
    started_total: int = Field(ge=0)
    rejected_fraud_total: int = Field(ge=0)
    rejected_fraud_rate: float = Field(ge=0.0, le=1.0)
    last_start_at: datetime | None = None


class ReferralFraudCaseResponse(BaseModel):
    referral_id: int = Field(gt=0)
    referrer_user_id: int = Field(gt=0)
    referred_user_id: int = Field(gt=0)
    fraud_score: float = Field(ge=0.0)
    status: str
    created_at: datetime


class ReferralDashboardThresholdsResponse(BaseModel):
    min_started: int = Field(ge=0)
    max_fraud_rejected_rate: float = Field(ge=0.0, le=1.0)
    max_rejected_fraud_total: int = Field(ge=0)
    max_referrer_rejected_fraud: int = Field(ge=0)


class ReferralDashboardAlertsResponse(BaseModel):
    thresholds_applied: bool
    fraud_spike_detected: bool
    fraud_rate_above_threshold: bool
    rejected_fraud_total_above_threshold: bool
    referrer_spike_detected: bool


class ReferralDashboardResponse(BaseModel):
    generated_at: datetime
    window_hours: int = Field(ge=1, le=168)
    referrals_started_total: int = Field(ge=0)
    qualified_like_total: int = Field(ge=0)
    rewarded_total: int = Field(ge=0)
    rejected_fraud_total: int = Field(ge=0)
    canceled_total: int = Field(ge=0)
    qualification_rate: float = Field(ge=0.0, le=1.0)
    reward_rate: float = Field(ge=0.0, le=1.0)
    fraud_rejected_rate: float = Field(ge=0.0, le=1.0)
    status_counts: dict[str, int]
    top_referrers: list[ReferralTopReferrerStatsResponse]
    recent_fraud_cases: list[ReferralFraudCaseResponse]
    thresholds: ReferralDashboardThresholdsResponse
    alerts: ReferralDashboardAlertsResponse


class ReferralReviewCaseResponse(BaseModel):
    referral_id: int = Field(gt=0)
    referrer_user_id: int = Field(gt=0)
    referred_user_id: int = Field(gt=0)
    status: str
    fraud_score: float = Field(ge=0.0)
    created_at: datetime
    qualified_at: datetime | None = None
    rewarded_at: datetime | None = None


class ReferralReviewQueueResponse(BaseModel):
    generated_at: datetime
    window_hours: int = Field(ge=1, le=720)
    status_filter: str | None = None
    cases: list[ReferralReviewCaseResponse]


class ReferralReviewActionRequest(BaseModel):
    decision: str = Field(min_length=1, max_length=32)
    reason: str | None = Field(default=None, max_length=256)
    expected_current_status: str | None = Field(default=None, max_length=24)


class ReferralReviewActionResponse(BaseModel):
    referral: ReferralReviewCaseResponse
    idempotent_replay: bool


class ReferralNotificationEventResponse(BaseModel):
    id: int = Field(gt=0)
    event_type: str
    status: str
    created_at: datetime
    payload: dict[str, object]


class ReferralNotificationsFeedResponse(BaseModel):
    generated_at: datetime
    window_hours: int = Field(ge=1, le=720)
    event_type_filter: str | None = None
    total_events: int = Field(ge=0)
    by_type: dict[str, int]
    by_status: dict[str, int]
    events: list[ReferralNotificationEventResponse]


def _assert_internal_access(request: Request) -> None:
    settings = get_settings()
    client_ip = extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )

    if not is_client_ip_allowed(client_ip=client_ip, allowlist=settings.internal_api_allowlist):
        logger.warning("internal_referrals_auth_failed", reason="ip_not_allowed", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})

    if not is_internal_request_authenticated(
        request,
        expected_token=settings.internal_api_token,
    ):
        logger.warning("internal_referrals_auth_failed", reason="invalid_credentials", client_ip=client_ip)
        raise HTTPException(status_code=403, detail={"code": "E_FORBIDDEN"})


def _as_review_case(referral: Referral) -> ReferralReviewCaseResponse:
    return ReferralReviewCaseResponse(
        referral_id=int(referral.id),
        referrer_user_id=int(referral.referrer_user_id),
        referred_user_id=int(referral.referred_user_id),
        status=str(referral.status),
        fraud_score=float(referral.fraud_score),
        created_at=referral.created_at,
        qualified_at=referral.qualified_at,
        rewarded_at=referral.rewarded_at,
    )


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


@router.get("/internal/referrals/dashboard", response_model=ReferralDashboardResponse)
async def get_referrals_dashboard(
    request: Request,
    window_hours: int = Query(default=24, ge=1, le=168),
) -> ReferralDashboardResponse:
    _assert_internal_access(request)
    now_utc = datetime.now(timezone.utc)
    settings = get_settings()
    thresholds = get_referrals_alert_thresholds(settings)

    async with SessionLocal.begin() as session:
        snapshot = await build_referrals_dashboard_snapshot(
            session,
            now_utc=now_utc,
            window_hours=window_hours,
        )

    alert_state = evaluate_referrals_alert_state(snapshot=snapshot, thresholds=thresholds)
    return ReferralDashboardResponse(
        generated_at=snapshot.generated_at,
        window_hours=snapshot.window_hours,
        referrals_started_total=snapshot.referrals_started_total,
        qualified_like_total=snapshot.qualified_like_total,
        rewarded_total=snapshot.rewarded_total,
        rejected_fraud_total=snapshot.rejected_fraud_total,
        canceled_total=snapshot.canceled_total,
        qualification_rate=snapshot.qualification_rate,
        reward_rate=snapshot.reward_rate,
        fraud_rejected_rate=snapshot.fraud_rejected_rate,
        status_counts=snapshot.status_counts,
        top_referrers=[
            ReferralTopReferrerStatsResponse(**row) for row in snapshot.top_referrers
        ],
        recent_fraud_cases=[
            ReferralFraudCaseResponse(**row) for row in snapshot.recent_fraud_cases
        ],
        thresholds=ReferralDashboardThresholdsResponse(
            min_started=thresholds.min_started,
            max_fraud_rejected_rate=thresholds.max_fraud_rejected_rate,
            max_rejected_fraud_total=thresholds.max_rejected_fraud_total,
            max_referrer_rejected_fraud=thresholds.max_referrer_rejected_fraud,
        ),
        alerts=ReferralDashboardAlertsResponse(
            thresholds_applied=alert_state.thresholds_applied,
            fraud_spike_detected=alert_state.fraud_spike_detected,
            fraud_rate_above_threshold=alert_state.fraud_rate_above_threshold,
            rejected_fraud_total_above_threshold=alert_state.rejected_fraud_total_above_threshold,
            referrer_spike_detected=alert_state.referrer_spike_detected,
        ),
    )


@router.get("/internal/referrals/review-queue", response_model=ReferralReviewQueueResponse)
async def get_referrals_review_queue(
    request: Request,
    window_hours: int = Query(default=72, ge=1, le=720),
    status: str | None = Query(default="REJECTED_FRAUD", min_length=1, max_length=24),
    limit: int = Query(default=100, ge=1, le=300),
) -> ReferralReviewQueueResponse:
    _assert_internal_access(request)
    now_utc = datetime.now(timezone.utc)
    status_filter: str | None = None
    if status is not None:
        normalized_status = status.strip().upper()
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


@router.post("/internal/referrals/{referral_id}/review", response_model=ReferralReviewActionResponse)
async def apply_referral_review_decision(
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
            raise HTTPException(status_code=409, detail={"code": "E_REFERRAL_REVIEW_DECISION_CONFLICT"})

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


@router.get("/internal/referrals/events", response_model=ReferralNotificationsFeedResponse)
async def get_referrals_notification_events(
    request: Request,
    window_hours: int = Query(default=168, ge=1, le=720),
    event_type: str | None = Query(default=None, min_length=1, max_length=64),
    limit: int = Query(default=200, ge=1, le=500),
) -> ReferralNotificationsFeedResponse:
    _assert_internal_access(request)
    now_utc = datetime.now(timezone.utc)
    since_utc = now_utc - timedelta(hours=window_hours)

    normalized_type: str | None = None
    event_types: tuple[str, ...] = tuple(sorted(REFERRAL_NOTIFICATION_EVENT_TYPES))
    if event_type is not None:
        normalized_type = event_type.strip()
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
