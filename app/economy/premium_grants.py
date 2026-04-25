from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.ledger_repo import LedgerRepo


async def grant_premium_days(
    session: AsyncSession,
    *,
    user_id: int,
    grant_days: int,
    scope: str,
    now_utc: datetime,
    source: str,
    entry_type: str,
    entitlement_idempotency_key: str,
    ledger_idempotency_key: str,
    metadata: dict[str, object],
) -> Entitlement:
    if grant_days <= 0:
        raise ValueError("grant_days must be positive")

    active_entitlement = await EntitlementsRepo.get_active_premium_for_update(
        session,
        user_id,
        now_utc,
    )
    if active_entitlement is not None:
        base_end = (
            active_entitlement.ends_at
            if active_entitlement.ends_at and active_entitlement.ends_at > now_utc
            else now_utc
        )
        active_entitlement.ends_at = base_end + timedelta(days=grant_days)
        active_entitlement.updated_at = now_utc
        entitlement = active_entitlement
    else:
        entitlement = await EntitlementsRepo.create(
            session,
            entitlement=Entitlement(
                user_id=user_id,
                entitlement_type="PREMIUM",
                scope=scope,
                status="ACTIVE",
                starts_at=now_utc,
                ends_at=now_utc + timedelta(days=grant_days),
                source_purchase_id=None,
                idempotency_key=entitlement_idempotency_key,
                metadata_=metadata,
                created_at=now_utc,
                updated_at=now_utc,
            ),
        )

    await LedgerRepo.create(
        session,
        entry=LedgerEntry(
            user_id=user_id,
            purchase_id=None,
            entry_type=entry_type,
            asset="PREMIUM",
            direction="CREDIT",
            amount=grant_days,
            balance_after=None,
            source=source,
            idempotency_key=ledger_idempotency_key,
            metadata_=metadata,
            created_at=now_utc,
        ),
    )
    return entitlement


__all__ = ["grant_premium_days"]
