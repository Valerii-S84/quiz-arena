from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.users import User


async def fetch_user_language_distribution(session: AsyncSession) -> list[dict[str, object]]:
    language_expr = func.coalesce(
        func.nullif(func.lower(func.trim(User.language_code)), ""),
        "unknown",
    )
    rows = (
        await session.execute(
            select(language_expr.label("language"), func.count(User.id).label("users"))
            .group_by(language_expr)
            .order_by(func.count(User.id).desc(), language_expr.asc())
        )
    ).all()

    return [
        {
            "language": str(language or "unknown"),
            "users": int(total or 0),
        }
        for language, total in rows
    ]
