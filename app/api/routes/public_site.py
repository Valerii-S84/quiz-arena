from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func, select

from app.db.models.purchases import Purchase
from app.db.models.quiz_sessions import QuizSession
from app.db.models.users import User
from app.db.session import SessionLocal

router = APIRouter(tags=["public-site"])
STAR_TO_EUR_RATE = Decimal("0.02")


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


# Keep both paths for compatibility:
# - direct API calls use /api/stats
# - reverse-proxy setups with stripped /api prefix use /stats
@router.get("/stats")
@router.get("/api/stats")
async def get_stats() -> dict[str, int]:
    metrics = await _collect_public_metrics()
    users_raw = metrics.get("users_total")
    quizzes_raw = metrics.get("quizzes_total")
    users_total = users_raw if isinstance(users_raw, int) else 0
    quizzes_total = quizzes_raw if isinstance(quizzes_raw, int) else 0
    return {"users": users_total, "quizzes": quizzes_total}
