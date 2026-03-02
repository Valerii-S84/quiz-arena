from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.admin_audit_repo import AdminAuditRepo


async def write_admin_audit(
    session: AsyncSession,
    *,
    admin_email: str,
    action: str,
    target_type: str,
    target_id: str,
    payload: dict[str, object],
    ip: str | None,
) -> None:
    await AdminAuditRepo.log(
        session,
        admin_email=admin_email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
        ip=ip,
    )
