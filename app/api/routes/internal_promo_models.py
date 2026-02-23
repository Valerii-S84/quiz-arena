from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PromoRedeemRequest(BaseModel):
    user_id: int = Field(gt=0)
    promo_code: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=96)


class PromoRedeemResponse(BaseModel):
    redemption_id: UUID
    result_type: str
    premium_days: int | None = None
    premium_ends_at: datetime | None = None
    discount_percent: int | None = None
    reserved_until: datetime | None = None
    target_scope: str | None = None


class PromoDashboardResponse(BaseModel):
    generated_at: datetime
    window_hours: int = Field(ge=1, le=168)
    attempts_total: int = Field(ge=0)
    attempts_accepted: int = Field(ge=0)
    attempts_failed: int = Field(ge=0)
    acceptance_rate: float = Field(ge=0.0, le=1.0)
    failure_rate: float = Field(ge=0.0, le=1.0)
    attempt_failures_by_result: dict[str, int]
    redemptions_total: int = Field(ge=0)
    redemptions_applied: int = Field(ge=0)
    redemptions_by_status: dict[str, int]
    discount_redemptions_total: int = Field(ge=0)
    discount_redemptions_applied: int = Field(ge=0)
    discount_redemptions_reserved: int = Field(ge=0)
    discount_redemptions_expired: int = Field(ge=0)
    discount_conversion_rate: float = Field(ge=0.0, le=1.0)
    guard_window_minutes: int = Field(ge=1)
    guard_trigger_hashes: int = Field(ge=0)
    active_campaigns_total: int = Field(ge=0)
    paused_campaigns_total: int = Field(ge=0)
    paused_campaigns_recent: int = Field(ge=0)


class PromoCampaignResponse(BaseModel):
    id: int
    campaign_name: str
    promo_type: str
    target_scope: str
    status: str
    valid_from: datetime
    valid_until: datetime
    max_total_uses: int | None = None
    used_total: int = Field(ge=0)
    updated_at: datetime


class PromoCampaignStatusUpdateRequest(BaseModel):
    status: str = Field(min_length=1, max_length=16)
    reason: str | None = Field(default=None, max_length=256)
    expected_current_status: str | None = Field(default=None, max_length=16)


class PromoCampaignListResponse(BaseModel):
    campaigns: list[PromoCampaignResponse]


class PromoRefundRollbackRequest(BaseModel):
    purchase_id: UUID
    reason: str | None = Field(default=None, max_length=256)


class PromoRefundRollbackResponse(BaseModel):
    purchase_id: UUID
    purchase_status: str
    promo_redemption_id: UUID | None = None
    promo_redemption_status: str | None = None
    promo_code_id: int | None = None
    promo_code_used_total: int | None = None
    idempotent_replay: bool
