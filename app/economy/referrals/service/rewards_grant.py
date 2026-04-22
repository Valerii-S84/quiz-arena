from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.ledger_repo import LedgerRepo
from app.economy.referrals.constants import REWARD_CODE_PREMIUM_STARTER


async def _grant_premium_starter_reward(
    session: AsyncSession,
    *,
    user_id: int,
    referral_id: int,
    now_utc: datetime,
) -> None:
    active_entitlement = await EntitlementsRepo.get_active_premium_for_update(
        session, user_id, now_utc
    )
    if active_entitlement is not None:
        base_end = (
            active_entitlement.ends_at
            if active_entitlement.ends_at and active_entitlement.ends_at > now_utc
            else now_utc
        )
        active_entitlement.ends_at = base_end + timedelta(days=7)
        active_entitlement.updated_at = now_utc
    else:
        await EntitlementsRepo.create(
            session,
            entitlement=Entitlement(
                user_id=user_id,
                entitlement_type="PREMIUM",
                scope="PREMIUM_STARTER",
                status="ACTIVE",
                starts_at=now_utc,
                ends_at=now_utc + timedelta(days=7),
                source_purchase_id=None,
                idempotency_key=f"referral:reward:premium:{referral_id}",
                metadata_={"reward_code": REWARD_CODE_PREMIUM_STARTER},
                created_at=now_utc,
                updated_at=now_utc,
            ),
        )

    await LedgerRepo.create(
        session,
        entry=LedgerEntry(
            user_id=user_id,
            purchase_id=None,
            entry_type="REFERRAL_REWARD",
            asset="PREMIUM",
            direction="CREDIT",
            amount=7,
            balance_after=None,
            source="REFERRAL",
            idempotency_key=f"referral:reward:premium_ledger:{referral_id}",
            metadata_={"reward_code": REWARD_CODE_PREMIUM_STARTER},
            created_at=now_utc,
        ),
    )


async def _grant_reward(
    session: AsyncSession,
    *,
    user_id: int,
    referral_id: int,
    reward_code: str,
    now_utc: datetime,
) -> None:
    if reward_code != REWARD_CODE_PREMIUM_STARTER:
        raise ValueError(f"unsupported reward code: {reward_code}")
    await _grant_premium_starter_reward(
        session,
        user_id=user_id,
        referral_id=referral_id,
        now_utc=now_utc,
    )
