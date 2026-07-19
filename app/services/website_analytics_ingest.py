from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import structlog
from fastapi import Request

from app.api.routes.website_analytics_models import WebsiteAnalyticsEventPayload
from app.core.config import Settings
from app.db.models.website_events import WebsiteEvent
from app.economy.energy.constants import BERLIN_TIMEZONE
from app.services.admin.cache import get_redis_client
from app.services.internal_auth import extract_client_ip

WEBSITE_ANALYTICS_RATE_LIMIT_PREFIX = "qa_website_analytics:rate_limit:"
WEBSITE_ANALYTICS_RATE_LIMIT_WINDOW_SECONDS = 60
VISITOR_HASH_FALLBACK_SALT = "quiz-arena-website-analytics-v1"

logger = structlog.get_logger(__name__)


def _contains_control_character(value: str) -> bool:
    return any(ord(char) < 32 for char in value)


def normalize_public_path(raw_path: str) -> str | None:
    path = raw_path.strip()
    if not path.startswith("/") or path.startswith("//"):
        return None
    if _contains_control_character(path):
        return None

    path = path.split("#", maxsplit=1)[0].split("?", maxsplit=1)[0]
    if not path:
        return "/"
    return path[:512]


def _normalize_referrer(raw_referrer: str | None) -> str | None:
    if raw_referrer is None:
        return None
    referrer = raw_referrer.strip()
    if not referrer or _contains_control_character(referrer):
        return None
    return referrer[:512]


def _visitor_salt(settings: Settings) -> str:
    configured_salt = getattr(settings, "website_analytics_visitor_salt", "")
    normalized = str(configured_salt or "").strip()
    return normalized or VISITOR_HASH_FALLBACK_SALT


def hash_visitor_id(visitor_id: str, settings: Settings) -> str:
    return hmac.new(
        _visitor_salt(settings).encode("utf-8"),
        visitor_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _hash_rate_limit_bucket(bucket: str, settings: Settings) -> str:
    return hmac.new(
        _visitor_salt(settings).encode("utf-8"),
        bucket.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _normalize_event_timestamp(value: datetime | None, now_utc: datetime) -> datetime:
    if value is None:
        return now_utc
    event_time = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    event_time = event_time.astimezone(timezone.utc)

    if event_time > now_utc + timedelta(minutes=5):
        return now_utc
    if event_time < now_utc - timedelta(days=7):
        return now_utc
    return event_time


async def is_website_analytics_rate_limited(request: Request, settings: Settings) -> bool:
    limit = max(1, int(getattr(settings, "website_analytics_rate_limit_per_minute", 180)))
    client = await get_redis_client(settings)
    if client is None:
        return False

    client_ip = extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )
    key = f"{WEBSITE_ANALYTICS_RATE_LIMIT_PREFIX}{_hash_rate_limit_bucket(client_ip or 'unknown', settings)}"
    try:
        count = await client.incr(key)
        ttl_seconds_remaining = await client.ttl(key)
        if int(count) == 1 or int(ttl_seconds_remaining) < 0:
            await client.expire(key, WEBSITE_ANALYTICS_RATE_LIMIT_WINDOW_SECONDS)
    except Exception:
        logger.warning("website_analytics_rate_limit_unavailable")
        return False

    return int(count) > limit


def build_website_event(
    payload: WebsiteAnalyticsEventPayload,
    *,
    settings: Settings,
    now_utc: datetime,
) -> WebsiteEvent | None:
    path = normalize_public_path(payload.path)
    if path is None:
        return None

    event_time = _normalize_event_timestamp(payload.timestamp, now_utc)
    return WebsiteEvent(
        id=uuid4(),
        event_type=payload.event_type,
        visitor_hash=hash_visitor_id(payload.visitor_id, settings),
        path=path,
        referrer=_normalize_referrer(payload.referrer),
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
        created_at=event_time,
        local_date_berlin=event_time.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date(),
        event_metadata=payload.metadata,
    )
