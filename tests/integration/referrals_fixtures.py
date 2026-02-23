from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from aiogram.types import User as TelegramUser

from app.db.models.quiz_attempts import QuizAttempt
from app.db.models.quiz_sessions import QuizSession
from app.db.models.referrals import Referral
from app.db.models.users import User
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.energy.constants import BERLIN_TIMEZONE

UTC = timezone.utc


def _berlin_date(at_utc: datetime) -> date:
    return at_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()


def _telegram_user(telegram_user_id: int) -> TelegramUser:
    return TelegramUser(
        id=telegram_user_id,
        is_bot=False,
        first_name="Referral",
        username=None,
        language_code="de",
    )


async def _create_user(seed: str) -> User:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=50_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"X{uuid4().hex[:10].upper()}",
            username=None,
            first_name="User",
            referred_by_user_id=None,
        )
        return user


async def _seed_attempts(
    *,
    user_id: int,
    attempts_per_day: int,
    day_offsets: tuple[int, ...],
    now_utc: datetime,
) -> None:
    async with SessionLocal.begin() as session:
        for day_offset in day_offsets:
            base = now_utc - timedelta(days=day_offset)
            local_date = _berlin_date(base)
            for idx in range(attempts_per_day):
                started_at = base + timedelta(minutes=idx)
                session_id = uuid4()
                session.add(
                    QuizSession(
                        id=session_id,
                        user_id=user_id,
                        mode_code="QUICK_MIX_A1A2",
                        source="MENU",
                        status="COMPLETED",
                        energy_cost_total=1,
                        question_id=f"q_{day_offset}_{idx}",
                        started_at=started_at,
                        completed_at=started_at,
                        local_date_berlin=local_date,
                        idempotency_key=f"seed:session:{user_id}:{day_offset}:{idx}",
                    )
                )
                await session.flush()
                session.add(
                    QuizAttempt(
                        session_id=session_id,
                        user_id=user_id,
                        question_id=f"q_{day_offset}_{idx}",
                        is_correct=True,
                        answered_at=started_at,
                        response_ms=1000,
                        idempotency_key=f"seed:attempt:{user_id}:{day_offset}:{idx}",
                    )
                )
        await session.flush()


async def _create_referral_row(
    *,
    referrer_user_id: int,
    referred_user_id: int,
    referral_code: str,
    status: str,
    created_at: datetime,
    qualified_at: datetime | None = None,
) -> None:
    async with SessionLocal.begin() as session:
        session.add(
            Referral(
                referrer_user_id=referrer_user_id,
                referred_user_id=referred_user_id,
                referral_code=referral_code,
                status=status,
                qualified_at=qualified_at,
                rewarded_at=None,
                fraud_score=0,
                created_at=created_at,
            )
        )
        await session.flush()
