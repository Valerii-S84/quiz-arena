from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.db.models.contact_requests import ContactRequest as ContactRequestModel
from app.db.models.purchases import Purchase
from app.db.models.quiz_sessions import QuizSession
from app.db.models.users import User
from app.db.session import SessionLocal

router = APIRouter(tags=["public-site"])
STAR_TO_EUR_RATE = Decimal("0.02")


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


async def _collect_public_metrics() -> dict[str, object]:
    async with SessionLocal.begin() as session:
        users_total = int((await session.execute(select(func.count(User.id)))).scalar_one() or 0)
        quizzes_total = int(
            (await session.execute(select(func.count(QuizSession.id)))).scalar_one() or 0
        )
        purchases_total = int(
            (
                await session.execute(
                    select(func.count(Purchase.id)).where(Purchase.paid_at.is_not(None))
                )
            ).scalar_one()  # noqa: E501
            or 0
        )
        stars_total = int(
            (
                await session.execute(
                    select(func.coalesce(func.sum(Purchase.stars_amount), 0)).where(
                        Purchase.paid_at.is_not(None)
                    )
                )
            ).scalar_one()
            or 0
        )

    return {
        "users_total": users_total,
        "quizzes_total": quizzes_total,
        "purchases_total": purchases_total,
        "revenue_stars_total": stars_total,
        "revenue_eur_total": round(float(Decimal(stars_total) * STAR_TO_EUR_RATE), 2),
    }


@router.get("/public/metrics")
async def get_public_metrics() -> dict[str, object]:
    return await _collect_public_metrics()


@router.get("/api/stats")
async def get_stats() -> dict[str, int]:
    metrics = await _collect_public_metrics()
    users_raw = metrics.get("users_total")
    quizzes_raw = metrics.get("quizzes_total")
    users_total = users_raw if isinstance(users_raw, int) else 0
    quizzes_total = quizzes_raw if isinstance(quizzes_raw, int) else 0
    return {"users": users_total, "quizzes": quizzes_total}


@router.post("/api/contact", status_code=status.HTTP_202_ACCEPTED)
async def submit_contact(payload: ContactPayload) -> dict[str, bool]:
    if payload.request_type == "student":
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
    if payload.request_type == "partner":
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

    normalized_payload = payload.model_dump(by_alias=True, exclude_none=True)
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
