from __future__ import annotations

import hashlib
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings, get_settings
from app.db.models.contact_requests import ContactRequest as ContactRequestModel
from app.db.session import SessionLocal
from app.services.admin.cache import get_redis_client
from app.services.internal_auth import extract_client_ip

router = APIRouter(tags=["public-site"])

_PUBLIC_CONTACT_RATE_LIMIT_ATTEMPTS = 3
_PUBLIC_CONTACT_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
_PUBLIC_CONTACT_RATE_LIMIT_KEY_PREFIX = "qa_public_contact:submit:"


class ContactPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    request_type: Literal["student", "partner"] = Field(alias="type")
    name: str = Field(min_length=1, max_length=200)
    contact: str = Field(min_length=3, max_length=200)
    age_group: str | None = Field(default=None, alias="ageGroup", max_length=64)
    level: str | None = Field(default=None, max_length=32)
    goals: list[str] | None = Field(default=None)
    learning_format: str | None = Field(default=None, alias="format", max_length=120)
    time_slots: list[str] | None = Field(default=None, alias="timeSlots")
    frequency: str | None = Field(default=None, max_length=64)
    budget: str | None = Field(default=None, max_length=64)
    partner_type: str | None = Field(default=None, alias="partnerType", max_length=120)
    cooperation_type: str | None = Field(default=None, alias="cooperationType", max_length=120)
    country: str | None = Field(default=None, max_length=120)
    student_count: str | None = Field(default=None, alias="studentCount", max_length=64)
    offerings: list[str] | None = Field(default=None)
    website: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=120)
    idea: str | None = Field(default=None, max_length=1000)
    start_timeline: str | None = Field(default=None, alias="startTimeline", max_length=120)
    message: str | None = Field(default=None, max_length=500)


def _is_blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _is_empty_items(items: list[str] | None) -> bool:
    if not items:
        return True
    return not any(item.strip() for item in items)


def _first_non_blank(*values: str | None) -> str | None:
    for value in values:
        if value is not None and value.strip():
            return value
    return None


def _contact_rate_limit_bucket(*, request: Request, settings: Settings) -> str:
    client_ip = extract_client_ip(
        request,
        trusted_proxies=getattr(settings, "internal_api_trusted_proxies", ""),
    )
    if client_ip is not None:
        return client_ip
    return "unknown"


def _contact_rate_limit_key(bucket: str) -> str:
    bucket_hash = hashlib.sha256(bucket.encode("utf-8")).hexdigest()
    return f"{_PUBLIC_CONTACT_RATE_LIMIT_KEY_PREFIX}{bucket_hash}"


async def _enforce_contact_rate_limit(*, request: Request, settings: Settings) -> None:
    client = await get_redis_client(settings)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "E_CONTACT_TEMPORARILY_UNAVAILABLE"},
        )

    key = _contact_rate_limit_key(_contact_rate_limit_bucket(request=request, settings=settings))
    try:
        attempts = await client.incr(key)
        if attempts == 1 or await client.ttl(key) < 0:
            await client.expire(key, _PUBLIC_CONTACT_RATE_LIMIT_WINDOW_SECONDS)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "E_CONTACT_TEMPORARILY_UNAVAILABLE"},
        ) from exc

    if attempts > _PUBLIC_CONTACT_RATE_LIMIT_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={"code": "E_RATE_LIMITED"}
        )


def _validate_student_payload(payload: ContactPayload) -> None:
    if _is_blank(payload.age_group):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "E_AGE_GROUP_REQUIRED"},
        )
    if _is_blank(payload.level):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "E_LEVEL_REQUIRED"},
        )
    if _is_empty_items(payload.goals):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "E_GOALS_REQUIRED"},
        )
    if _is_blank(payload.learning_format):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "E_FORMAT_REQUIRED"},
        )
    if _is_empty_items(payload.time_slots):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "E_TIME_SLOTS_REQUIRED"},
        )
    if _is_blank(payload.frequency):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "E_FREQUENCY_REQUIRED"},
        )


def _validate_partner_payload(payload: ContactPayload) -> None:
    partner_type = _first_non_blank(payload.partner_type, payload.cooperation_type)
    if partner_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "E_PARTNER_TYPE_REQUIRED"},
        )
    if _is_blank(payload.country):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "E_COUNTRY_REQUIRED"},
        )
    if _is_blank(payload.student_count):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "E_STUDENT_COUNT_REQUIRED"},
        )
    if _is_empty_items(payload.offerings):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "E_OFFERINGS_REQUIRED"},
        )
    if _is_blank(payload.idea):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "E_IDEA_REQUIRED"},
        )
    if _is_blank(payload.start_timeline):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "E_START_TIMELINE_REQUIRED"},
        )


# Keep both paths for compatibility:
# - direct API calls use /api/contact
# - reverse-proxy setups with stripped /api prefix use /contact
@router.post("/contact", status_code=status.HTTP_202_ACCEPTED)
@router.post("/api/contact", status_code=status.HTTP_202_ACCEPTED)
async def submit_contact(
    payload: ContactPayload,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    if not _is_blank(payload.company):
        return {"ok": True}

    await _enforce_contact_rate_limit(request=request, settings=settings)

    if payload.request_type == "student":
        _validate_student_payload(payload)
    if payload.request_type == "partner":
        _validate_partner_payload(payload)

    normalized_payload = payload.model_dump(by_alias=True, exclude_none=True)
    normalized_payload.pop("company", None)
    if payload.request_type == "partner":
        normalized_partner_type = _first_non_blank(payload.partner_type, payload.cooperation_type)
        if normalized_partner_type is not None:
            normalized_payload["partnerType"] = normalized_partner_type

    async with SessionLocal.begin() as session:
        session.add(
            ContactRequestModel(
                request_type=payload.request_type,
                name=payload.name.strip(),
                contact=payload.contact.strip(),
                payload=normalized_payload,
            )
        )

    # TODO: Forward saved contact requests to CRM/Telegram notification channel.
    return {"ok": True}
