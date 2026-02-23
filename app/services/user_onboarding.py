from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from aiogram.types import User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.referral_codes import generate_referral_code
from app.db.repo.users_repo import UsersRepo
from app.economy.energy.service import EnergyService
from app.economy.referrals.service import ReferralService
from app.economy.streak.service import StreakService


@dataclass(slots=True)
class HomeSnapshot:
    user_id: int
    free_energy: int
    paid_energy: int
    current_streak: int


class UserOnboardingService:
    @staticmethod
    async def _generate_unique_referral_code(session: AsyncSession) -> str:
        for _ in range(10):
            referral_code = generate_referral_code()
            existing = await UsersRepo.get_by_referral_code(session, referral_code)
            if existing is None:
                return referral_code
        raise RuntimeError("unable to generate unique referral code")

    @staticmethod
    async def ensure_home_snapshot(
        session: AsyncSession,
        *,
        telegram_user: TelegramUser,
        start_payload: str | None = None,
    ) -> HomeSnapshot:
        now_utc = datetime.now(timezone.utc)

        user = await UsersRepo.get_by_telegram_user_id(session, telegram_user.id)
        if user is None:
            referral_code = await UserOnboardingService._generate_unique_referral_code(session)
            user = await UsersRepo.create(
                session,
                telegram_user_id=telegram_user.id,
                referral_code=referral_code,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                referred_by_user_id=None,
                language_code=telegram_user.language_code or "de",
                timezone="Europe/Berlin",
            )

            await EnergyService.initialize_user_state(session, user_id=user.id, now_utc=now_utc)
            await StreakService.sync_rollover(session, user_id=user.id, now_utc=now_utc)
            referral_code_from_payload = ReferralService.extract_referral_code_from_start_payload(
                start_payload
            )
            if referral_code_from_payload is not None:
                await ReferralService.register_start_for_new_user(
                    session,
                    referred_user=user,
                    referral_code=referral_code_from_payload,
                    now_utc=now_utc,
                )

        await UsersRepo.touch_last_seen(session, user.id, now_utc)
        energy_snapshot = await EnergyService.sync_energy_clock(
            session, user_id=user.id, now_utc=now_utc
        )
        streak_snapshot = await StreakService.sync_rollover(
            session, user_id=user.id, now_utc=now_utc
        )

        return HomeSnapshot(
            user_id=user.id,
            free_energy=energy_snapshot.free_energy,
            paid_energy=energy_snapshot.paid_energy,
            current_streak=streak_snapshot.current_streak,
        )
