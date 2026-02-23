from __future__ import annotations

from datetime import datetime

from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal


def format_remaining_hhmm(*, now_utc: datetime, expires_at: datetime) -> tuple[int, int]:
    remaining_seconds = max(0, int((expires_at - now_utc).total_seconds()))
    return remaining_seconds // 3600, (remaining_seconds % 3600) // 60


async def resolve_telegram_targets(user_ids: set[int]) -> dict[int, int]:
    if not user_ids:
        return {}
    async with SessionLocal.begin() as session:
        users = await UsersRepo.list_by_ids(session, list(user_ids))
    return {int(user.id): int(user.telegram_user_id) for user in users}
