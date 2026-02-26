from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.models.daily_push_logs import DailyPushLog
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.workers.tasks import daily_challenge_async


class _FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        current = datetime(2026, 2, 26, 7, 0, tzinfo=timezone.utc)
        if tz is None:
            return current.replace(tzinfo=None)
        return current.astimezone(tz)


class _DummyBotSession:
    async def close(self) -> None:
        return None


class _DummyBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id: int, text: str, reply_markup) -> None:
        del reply_markup
        self.sent_messages.append((chat_id, text))


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=70_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"P{uuid4().hex[:10]}",
            username=None,
            first_name="Push",
            referred_by_user_id=None,
        )
        return int(user.id)


@pytest.mark.asyncio
async def test_daily_push_worker_is_idempotent_for_same_day(monkeypatch) -> None:
    await _create_user("daily-push-idempotent")

    bot = _DummyBot()
    monkeypatch.setattr(daily_challenge_async, "build_bot", lambda: bot)
    monkeypatch.setattr(daily_challenge_async, "datetime", _FrozenDateTime)

    first = await daily_challenge_async.run_daily_push_notifications_async(batch_size=100)
    second = await daily_challenge_async.run_daily_push_notifications_async(batch_size=100)

    assert int(first["sent_total"]) == 1
    assert int(second["sent_total"]) == 0
    assert len(bot.sent_messages) == 1

    async with SessionLocal.begin() as session:
        logged = await session.scalar(select(func.count(DailyPushLog.user_id)))
    assert int(logged or 0) == 1
