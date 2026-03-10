from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admins import Admin


class AdminsRepo:
    @staticmethod
    async def get_by_email(session: AsyncSession, *, email: str) -> Admin | None:
        stmt = select(Admin).where(Admin.email == email)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create(
        session: AsyncSession,
        *,
        email: str,
        role: str,
    ) -> Admin:
        admin = await AdminsRepo.get_by_email(session, email=email)
        now_utc = datetime.now(timezone.utc)
        if admin is None:
            admin = Admin(
                email=email,
                role=role,
                created_at=now_utc,
                updated_at=now_utc,
            )
            session.add(admin)
            await session.flush()
            return admin
        if admin.role != role:
            admin.role = role
            admin.updated_at = now_utc
        return admin
