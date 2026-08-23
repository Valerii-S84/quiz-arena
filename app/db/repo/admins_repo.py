from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admins import Admin


class AdminsRepo:
    @staticmethod
    async def get_by_email(session: AsyncSession, *, email: str) -> Admin | None:
        normalized_email = email.strip().lower()
        if not normalized_email:
            return None
        stmt = select(Admin).where(func.lower(func.trim(Admin.email)) == normalized_email)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create(
        session: AsyncSession,
        *,
        email: str,
        role: str,
        enabled: bool = False,
    ) -> Admin:
        normalized_email = email.strip().lower()
        admin = await AdminsRepo.get_by_email(session, email=normalized_email)
        now_utc = datetime.now(timezone.utc)
        if admin is None:
            admin = Admin(
                email=normalized_email,
                role=role,
                enabled=enabled,
                created_at=now_utc,
                updated_at=now_utc,
            )
            session.add(admin)
            await session.flush()
            return admin
        return admin
