from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin_audit_log import AdminAuditLog


class AdminAuditRepo:
    @staticmethod
    async def log(
        session: AsyncSession,
        *,
        admin_email: str,
        action: str,
        target_type: str,
        target_id: str,
        payload: dict[str, object],
        ip: str | None,
    ) -> AdminAuditLog:
        entry = AdminAuditLog(
            admin_email=admin_email,
            action=action,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
            ip=ip,
            created_at=datetime.now(timezone.utc),
        )
        session.add(entry)
        await session.flush()
        return entry
