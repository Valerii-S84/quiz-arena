from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class PromoCreateRequest(BaseModel):
    code: str = Field(min_length=4, max_length=64)
    campaign_name: str | None = Field(default=None, max_length=128)
    discount_type: str | None = Field(default=None, pattern="^(PERCENT|FIXED|FREE)$")
    discount_value: float | None = Field(default=None, gt=0)
    applicable_products: list[str] | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_total_uses: int = Field(default=0, ge=0)
    max_per_user: int = Field(default=1, ge=1)
    type: str | None = None
    value: float | None = Field(default=None, gt=0)
    product_id: str | None = None
    max_uses: int | None = Field(default=None, ge=0)
    channel_tag: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validate_dates(self) -> PromoCreateRequest:
        _ensure_valid_date_range(valid_from=self.valid_from, valid_until=self.valid_until)
        return self


class PromoBulkCreateRequest(BaseModel):
    count: int = Field(ge=1, le=1000)
    prefix: str | None = Field(default=None, max_length=6)
    campaign_name: str | None = Field(default=None, max_length=128)
    discount_type: str | None = Field(default=None, pattern="^(PERCENT|FIXED|FREE)$")
    discount_value: float | None = Field(default=None, gt=0)
    applicable_products: list[str] | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_total_uses: int = Field(default=0, ge=0)
    max_per_user: int = Field(default=1, ge=1)
    type: str | None = None
    value: float | None = Field(default=None, gt=0)
    product_id: str | None = None
    max_uses: int | None = Field(default=None, ge=0)
    channel_tag: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def validate_dates(self) -> PromoBulkCreateRequest:
        _ensure_valid_date_range(valid_from=self.valid_from, valid_until=self.valid_until)
        return self


class PromoPatchRequest(BaseModel):
    campaign_name: str | None = Field(default=None, max_length=128)
    discount_type: str | None = Field(default=None, pattern="^(PERCENT|FIXED|FREE)$")
    discount_value: float | None = Field(default=None, gt=0)
    applicable_products: list[str] | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_total_uses: int | None = Field(default=None, ge=0)
    max_per_user: int | None = Field(default=None, ge=1)
    type: str | None = None
    value: float | None = Field(default=None, gt=0)
    product_id: str | None = None
    max_uses: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_dates(self) -> PromoPatchRequest:
        _ensure_valid_date_range(valid_from=self.valid_from, valid_until=self.valid_until)
        return self


class PromoRevokeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=256)


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _ensure_valid_date_range(*, valid_from: datetime | None, valid_until: datetime | None) -> None:
    if valid_from is None or valid_until is None:
        return
    if _is_timezone_aware(valid_from) != _is_timezone_aware(valid_until):
        raise ValueError("valid_from and valid_until must use matching timezone awareness")
    if valid_until <= valid_from:
        raise ValueError("valid_until must be after valid_from")
