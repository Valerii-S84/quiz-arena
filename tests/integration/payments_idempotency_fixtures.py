from __future__ import annotations

from datetime import timezone
from uuid import uuid4

from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from tests.integration.stable_ids import stable_telegram_user_id

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=stable_telegram_user_id(prefix=10_000_000_000, seed=seed),
            referral_code=f"R{uuid4().hex[:10]}",
            username=None,
            first_name="Integration",
            referred_by_user_id=None,
        )
        return user.id
