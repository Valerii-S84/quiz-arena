from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repo.promo_audit_repo import PromoAuditRepo


async def write_promo_audit(
    session: AsyncSession,
    *,
    admin_id: UUID,
    action: str,
    promo_code_id: int | None,
    details: dict[str, object],
) -> None:
    await PromoAuditRepo.log(
        session,
        admin_id=admin_id,
        action=action,
        promo_code_id=promo_code_id,
        details=details,
    )
