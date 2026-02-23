from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.models.mode_access import ModeAccess
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.mode_access_repo import ModeAccessRepo
from app.economy.energy.service import EnergyService
from app.economy.purchases.catalog import MEGA_PACK_MODE_CODES
from app.economy.referrals.constants import REWARD_CODE_MEGA_PACK, REWARD_CODE_PREMIUM_STARTER


async def _grant_mega_pack_reward(
    session: AsyncSession,
    *,
    user_id: int,
    referral_id: int,
    now_utc: datetime,
) -> None:
    await EnergyService.credit_paid_energy(
        session,
        user_id=user_id,
        amount=15,
        idempotency_key=f"referral:reward:energy:{referral_id}",
        now_utc=now_utc,
        source="REFERRAL",
    )

    await LedgerRepo.create(
        session,
        entry=LedgerEntry(
            user_id=user_id,
            purchase_id=None,
            entry_type="REFERRAL_REWARD",
            asset="MODE_ACCESS",
            direction="CREDIT",
            amount=1,
            balance_after=None,
            source="REFERRAL",
            idempotency_key=f"referral:reward:mode_access:{referral_id}",
            metadata_={"reward_code": REWARD_CODE_MEGA_PACK},
            created_at=now_utc,
        ),
    )

    for mode_code in MEGA_PACK_MODE_CODES:
        existing = await ModeAccessRepo.get_by_idempotency_key(
            session,
            idempotency_key=f"referral:reward:mode:{referral_id}:{mode_code}",
        )
        if existing is not None:
            continue
        latest_end = await ModeAccessRepo.get_latest_active_end(
            session,
            user_id=user_id,
            mode_code=mode_code,
            source="MEGA_PACK",
            now_utc=now_utc,
        )
        starts_at = latest_end if latest_end is not None and latest_end > now_utc else now_utc
        ends_at = starts_at + timedelta(hours=24)
        await ModeAccessRepo.create(
            session,
            mode_access=ModeAccess(
                user_id=user_id,
                mode_code=mode_code,
                source="MEGA_PACK",
                starts_at=starts_at,
                ends_at=ends_at,
                status="ACTIVE",
                source_purchase_id=None,
                idempotency_key=f"referral:reward:mode:{referral_id}:{mode_code}",
                created_at=now_utc,
            ),
        )


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
    if reward_code == REWARD_CODE_PREMIUM_STARTER:
        await _grant_premium_starter_reward(
            session,
            user_id=user_id,
            referral_id=referral_id,
            now_utc=now_utc,
        )
        return
    await _grant_mega_pack_reward(
        session,
        user_id=user_id,
        referral_id=referral_id,
        now_utc=now_utc,
    )
