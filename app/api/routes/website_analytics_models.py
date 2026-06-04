from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MetadataValue = str | int | float | bool | None


class WebsiteAnalyticsEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["page_view", "telegram_cta_click"]
    visitor_id: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    path: str = Field(min_length=1, max_length=512)
    referrer: str | None = Field(default=None, max_length=512)
    utm_source: str | None = Field(default=None, max_length=120)
    utm_medium: str | None = Field(default=None, max_length=120)
    utm_campaign: str | None = Field(default=None, max_length=160)
    timestamp: datetime | None = None
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @field_validator("referrer", "utm_source", "utm_medium", "utm_campaign")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("metadata")
    @classmethod
    def _limit_metadata(cls, metadata: dict[str, MetadataValue]) -> dict[str, MetadataValue]:
        normalized: dict[str, MetadataValue] = {}
        for raw_key, raw_value in list(metadata.items())[:12]:
            key = str(raw_key).strip()[:64]
            if not key:
                continue
            if isinstance(raw_value, str):
                normalized[key] = raw_value.strip()[:200]
                continue
            normalized[key] = raw_value
        return normalized


class WebsiteAnalyticsTotals(BaseModel):
    page_views_total: int = Field(ge=0)
    unique_visitors_total: int = Field(ge=0)
    telegram_cta_clicks_total: int = Field(ge=0)


class WebsiteAnalyticsDailyPoint(BaseModel):
    date: date
    unique_visitors: int = Field(ge=0)
    page_views: int = Field(ge=0)
    telegram_cta_clicks: int = Field(ge=0)


class WebsiteAnalyticsTopPage(BaseModel):
    path: str
    page_views: int = Field(ge=0)
    unique_visitors: int = Field(ge=0)
    telegram_cta_clicks: int = Field(ge=0)


class WebsiteAnalyticsOverviewResponse(BaseModel):
    generated_at: datetime
    days: int = Field(ge=1, le=90)
    totals: WebsiteAnalyticsTotals
    daily_series: list[WebsiteAnalyticsDailyPoint]
    top_pages: list[WebsiteAnalyticsTopPage]
