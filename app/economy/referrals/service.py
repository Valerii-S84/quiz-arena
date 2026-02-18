from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.models.mode_access import ModeAccess
from app.db.models.referrals import Referral
from app.db.models.users import User
from app.db.repo.entitlements_repo import EntitlementsRepo
from app.db.repo.ledger_repo import LedgerRepo
from app.db.repo.mode_access_repo import ModeAccessRepo
from app.db.repo.quiz_attempts_repo import QuizAttemptsRepo
from app.db.repo.referrals_repo import ReferralsRepo
from app.db.repo.users_repo import UsersRepo
from app.economy.energy.constants import BERLIN_TIMEZONE
from app.economy.energy.service import EnergyService
from app.economy.purchases.catalog import MEGA_PACK_MODE_CODES
from app.economy.referrals.constants import (
    DEFAULT_REFERRAL_REWARD_CODE,
    FRAUD_SCORE_CYCLIC,
    FRAUD_SCORE_VELOCITY,
    QUALIFICATION_MIN_ATTEMPTS,
    QUALIFICATION_MIN_LOCAL_DAYS,
    QUALIFICATION_WINDOW,
    QUALIFIED_REFERRALS_PER_REWARD,
    REFERRAL_CYCLE_WINDOW,
    REFERRAL_REWARDS_PER_MONTH_CAP,
    REFERRAL_STARTS_DAILY_LIMIT,
    REWARD_CODE_MEGA_PACK,
    REWARD_CODE_PREMIUM_STARTER,
    REWARD_DELAY,
)

START_PAYLOAD_REFERRAL_RE = re.compile(r"^ref_([A-Za-z0-9]{3,16})$")


class ReferralService:
    @staticmethod
    def extract_referral_code_from_start_payload(start_payload: str | None) -> str | None:
        if not start_payload:
            return None
        matched = START_PAYLOAD_REFERRAL_RE.match(start_payload.strip())
        if matched is None:
            return None
        return matched.group(1).upper()

    @staticmethod
    def _berlin_datetime(now_utc: datetime) -> datetime:
        return now_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE))

    @staticmethod
    def _berlin_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
        local_now = ReferralService._berlin_datetime(now_utc)
        local_day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        local_day_end = local_day_start + timedelta(days=1)
        return (
            local_day_start.astimezone(now_utc.tzinfo),
            local_day_end.astimezone(now_utc.tzinfo),
        )

    @staticmethod
    def _berlin_month_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
        local_now = ReferralService._berlin_datetime(now_utc)
        local_month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if local_month_start.month == 12:
            local_next_month = local_month_start.replace(year=local_month_start.year + 1, month=1)
        else:
            local_next_month = local_month_start.replace(month=local_month_start.month + 1)
        return (
            local_month_start.astimezone(now_utc.tzinfo),
            local_next_month.astimezone(now_utc.tzinfo),
        )

    @staticmethod
    async def register_start_for_new_user(
        session: AsyncSession,
        *,
        referred_user: User,
        referral_code: str,
        now_utc: datetime,
    ) -> str | None:
        normalized_code = referral_code.strip().upper()
        if not normalized_code:
            return None

        existing = await ReferralsRepo.get_by_referred_user_id(
            session,
            referred_user_id=referred_user.id,
        )
        if existing is not None:
            return existing.status

        referrer = await UsersRepo.get_by_referral_code(session, normalized_code)
        if referrer is None:
            return None
        if referrer.id == referred_user.id:
            return None
        if referrer.telegram_user_id == referred_user.telegram_user_id:
            return None

        reverse_pair = await ReferralsRepo.get_reverse_pair_since(
            session,
            referrer_user_id=referrer.id,
            referred_user_id=referred_user.id,
            since_utc=now_utc - REFERRAL_CYCLE_WINDOW,
        )
        if reverse_pair is not None:
            await ReferralsRepo.create(
                session,
                referral=Referral(
                    referrer_user_id=referrer.id,
                    referred_user_id=referred_user.id,
                    referral_code=normalized_code,
                    status="REJECTED_FRAUD",
                    qualified_at=None,
                    rewarded_at=None,
                    fraud_score=FRAUD_SCORE_CYCLIC,
                    created_at=now_utc,
                ),
            )
            return "REJECTED_FRAUD"

        day_start_utc, day_end_utc = ReferralService._berlin_day_bounds_utc(now_utc)
        starts_today = await ReferralsRepo.count_referrer_starts_between(
            session,
            referrer_user_id=referrer.id,
            from_utc=day_start_utc,
            to_utc=day_end_utc,
        )
        is_velocity_abuse = starts_today + 1 > REFERRAL_STARTS_DAILY_LIMIT
        status = "REJECTED_FRAUD" if is_velocity_abuse else "STARTED"
        fraud_score = FRAUD_SCORE_VELOCITY if is_velocity_abuse else Decimal("0")

        await ReferralsRepo.create(
            session,
            referral=Referral(
                referrer_user_id=referrer.id,
                referred_user_id=referred_user.id,
                referral_code=normalized_code,
                status=status,
                qualified_at=None,
                rewarded_at=None,
                fraud_score=fraud_score,
                created_at=now_utc,
            ),
        )
        referred_user.referred_by_user_id = referrer.id
        return status

    @staticmethod
    async def run_qualification_checks(
        session: AsyncSession,
        *,
        now_utc: datetime,
        batch_size: int = 200,
    ) -> dict[str, int]:
        started_ids = await ReferralsRepo.list_started_ids(session, limit=batch_size)
        result = {
            "examined": len(started_ids),
            "qualified": 0,
            "canceled": 0,
            "rejected_fraud": 0,
        }

        for referral_id in started_ids:
            referral = await ReferralsRepo.get_by_id_for_update(session, referral_id=referral_id)
            if referral is None or referral.status != "STARTED":
                continue

            reverse_pair = await ReferralsRepo.get_reverse_pair_since(
                session,
                referrer_user_id=referral.referrer_user_id,
                referred_user_id=referral.referred_user_id,
                since_utc=now_utc - REFERRAL_CYCLE_WINDOW,
            )
            if reverse_pair is not None:
                referral.status = "REJECTED_FRAUD"
                referral.fraud_score = FRAUD_SCORE_CYCLIC
                result["rejected_fraud"] += 1
                continue

            referred_user = await UsersRepo.get_by_id(session, referral.referred_user_id)
            if referred_user is None or referred_user.status == "DELETED":
                referral.status = "CANCELED"
                result["canceled"] += 1
                continue

            qualification_window_end = referral.created_at + QUALIFICATION_WINDOW
            evaluation_window_end = min(now_utc, qualification_window_end)
            attempts_count = await QuizAttemptsRepo.count_user_attempts_between(
                session,
                user_id=referral.referred_user_id,
                from_utc=referral.created_at,
                to_utc=evaluation_window_end,
            )
            active_days_count = await QuizAttemptsRepo.count_user_active_local_days_between(
                session,
                user_id=referral.referred_user_id,
                from_utc=referral.created_at,
                to_utc=evaluation_window_end,
            )

            if (
                attempts_count >= QUALIFICATION_MIN_ATTEMPTS
                and active_days_count >= QUALIFICATION_MIN_LOCAL_DAYS
            ):
                referral.status = "QUALIFIED"
                referral.qualified_at = now_utc
                result["qualified"] += 1
                continue

            if now_utc >= qualification_window_end:
                referral.status = "CANCELED"
                result["canceled"] += 1

        return result

    @staticmethod
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

    @staticmethod
    async def _grant_premium_starter_reward(
        session: AsyncSession,
        *,
        user_id: int,
        referral_id: int,
        now_utc: datetime,
    ) -> None:
        active_entitlement = await EntitlementsRepo.get_active_premium_for_update(session, user_id, now_utc)
        if active_entitlement is not None:
            base_end = active_entitlement.ends_at if active_entitlement.ends_at and active_entitlement.ends_at > now_utc else now_utc
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

    @staticmethod
    async def _grant_reward(
        session: AsyncSession,
        *,
        user_id: int,
        referral_id: int,
        reward_code: str,
        now_utc: datetime,
    ) -> None:
        if reward_code == REWARD_CODE_PREMIUM_STARTER:
            await ReferralService._grant_premium_starter_reward(
                session,
                user_id=user_id,
                referral_id=referral_id,
                now_utc=now_utc,
            )
            return
        await ReferralService._grant_mega_pack_reward(
            session,
            user_id=user_id,
            referral_id=referral_id,
            now_utc=now_utc,
        )

    @staticmethod
    async def run_reward_distribution(
        session: AsyncSession,
        *,
        now_utc: datetime,
        batch_size: int = 200,
        reward_code: str = DEFAULT_REFERRAL_REWARD_CODE,
    ) -> dict[str, int]:
        qualified_before_utc = now_utc - REWARD_DELAY
        referrer_ids = await ReferralsRepo.list_referrer_ids_with_reward_candidates(
            session,
            qualified_before_utc=qualified_before_utc,
            limit=batch_size,
        )
        month_start_utc, next_month_start_utc = ReferralService._berlin_month_bounds_utc(now_utc)

        result = {
            "referrers_examined": len(referrer_ids),
            "rewards_granted": 0,
            "deferred_limit": 0,
        }

        for referrer_user_id in referrer_ids:
            referrals = await ReferralsRepo.list_for_referrer_for_update(
                session,
                referrer_user_id=referrer_user_id,
            )
            if not referrals:
                continue

            qualified_sequence = [
                referral
                for referral in referrals
                if referral.status in {"QUALIFIED", "DEFERRED_LIMIT", "REWARDED"}
                and referral.qualified_at is not None
            ]
            target_rewards_total = len(qualified_sequence) // QUALIFIED_REFERRALS_PER_REWARD
            if target_rewards_total == 0:
                continue

            rewarded_this_month = await ReferralsRepo.count_rewards_for_referrer_between(
                session,
                referrer_user_id=referrer_user_id,
                from_utc=month_start_utc,
                to_utc=next_month_start_utc,
            )

            for slot_index in range(target_rewards_total):
                anchor_idx = (slot_index + 1) * QUALIFIED_REFERRALS_PER_REWARD - 1
                referral = qualified_sequence[anchor_idx]
                if referral.qualified_at is None or referral.qualified_at > qualified_before_utc:
                    continue
                if referral.status == "REWARDED":
                    continue

                if rewarded_this_month >= REFERRAL_REWARDS_PER_MONTH_CAP:
                    if referral.status != "DEFERRED_LIMIT":
                        referral.status = "DEFERRED_LIMIT"
                        result["deferred_limit"] += 1
                    continue

                await ReferralService._grant_reward(
                    session,
                    user_id=referrer_user_id,
                    referral_id=referral.id,
                    reward_code=reward_code,
                    now_utc=now_utc,
                )
                referral.status = "REWARDED"
                referral.rewarded_at = now_utc
                rewarded_this_month += 1
                result["rewards_granted"] += 1

        return result
