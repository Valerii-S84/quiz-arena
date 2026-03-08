from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admins import Admin
from app.db.models.promo_audit_log import PromoAuditLog


class PromoAuditRepo:
    @staticmethod
    async def log(
        session: AsyncSession,
        *,
        admin_id: UUID,
        action: str,
        promo_code_id: int | None,
        details: dict[str, object],
    ) -> PromoAuditLog:
        entry = PromoAuditLog(
            id=uuid4(),
            admin_id=admin_id,
            action=action,
            promo_code_id=promo_code_id,
            details=details,
            created_at=datetime.now(timezone.utc),
        )
        session.add(entry)
        await session.flush()
        return entry

    @staticmethod
    async def list_for_promo(
        session: AsyncSession,
        *,
        promo_code_id: int,
        limit: int = 100,
    ) -> list[tuple[PromoAuditLog, str]]:
        stmt = (
            select(PromoAuditLog, Admin.email)
            .join(Admin, Admin.id == PromoAuditLog.admin_id)
            .where(PromoAuditLog.promo_code_id == promo_code_id)
            .order_by(PromoAuditLog.created_at.desc(), PromoAuditLog.id.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return [(row[0], str(row[1])) for row in result.all()]

    @staticmethod
    async def list_for_actions(
        session: AsyncSession,
        *,
        actions: Sequence[str],
    ) -> list[PromoAuditLog]:
        if not actions:
            return []
        stmt = select(PromoAuditLog).where(PromoAuditLog.action.in_(tuple(actions)))
        result = await session.execute(stmt)
        return list(result.scalars().all())
