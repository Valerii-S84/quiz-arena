from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.energy.constants import BERLIN_TIMEZONE

UTC = timezone.utc


def _berlin_date(at_utc: datetime) -> date:
    return at_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()


def _day_bounds_utc(local_date_berlin: date) -> tuple[datetime, datetime]:
    tz = ZoneInfo(BERLIN_TIMEZONE)
    start_local = datetime.combine(local_date_berlin, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


async def _create_user(seed: str, seen_at: datetime) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=80_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"A{uuid4().hex[:10].upper()}",
            username=None,
            first_name="Analytics",
            referred_by_user_id=None,
        )
        user.last_seen_at = seen_at
        return int(user.id)
