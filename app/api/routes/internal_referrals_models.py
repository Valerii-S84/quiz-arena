from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


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


DecimalType = Decimal
