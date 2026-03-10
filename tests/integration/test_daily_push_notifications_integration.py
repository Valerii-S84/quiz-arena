from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.db.models.daily_push_logs import DailyPushLog
from app.db.models.daily_runs import DailyRun
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.workers.tasks import daily_challenge_async
from tests.integration.stable_ids import stable_telegram_user_id


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
            telegram_user_id=stable_telegram_user_id(prefix=70_000_000_000, seed=seed),
            referral_code=f"P{uuid4().hex[:10]}",
            username=None,
            first_name="Push",
            referred_by_user_id=None,
        )
        return int(user.id)


async def _create_daily_run(*, user_id: int, berlin_date: date, status: str) -> None:
    completed_at = (
        datetime(2026, 2, 26, 7, 0, tzinfo=timezone.utc) if status == "COMPLETED" else None
    )
    current_question = 7 if status == "COMPLETED" else 3
    async with SessionLocal.begin() as session:
        session.add(
            DailyRun(
                id=uuid4(),
                user_id=user_id,
                berlin_date=berlin_date,
                current_question=current_question,
                score=2,
                status=status,
                started_at=datetime(2026, 2, 26, 6, 0, tzinfo=timezone.utc),
                completed_at=completed_at,
            )
        )


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


@pytest.mark.asyncio
async def test_daily_push_worker_sends_evening_reminder_after_morning_push(monkeypatch) -> None:
    await _create_user("daily-push-evening-reminder")

    bot = _DummyBot()
    monkeypatch.setattr(daily_challenge_async, "build_bot", lambda: bot)
    monkeypatch.setattr(daily_challenge_async, "datetime", _FrozenDateTime)

    first = await daily_challenge_async.run_daily_push_notifications_async(batch_size=100)
    second = await daily_challenge_async.run_daily_push_notifications_async(
        batch_size=100,
        push_kind="EVENING_REMINDER",
    )

    assert int(first["sent_total"]) == 1
    assert first["push_kind"] == "MORNING"
    assert int(second["sent_total"]) == 1
    assert second["push_kind"] == "EVENING_REMINDER"
    assert len(bot.sent_messages) == 2
    assert bot.sent_messages[1][1].startswith("⏰ Erinnerung:")

    async with SessionLocal.begin() as session:
        logged = await session.scalar(select(func.count(DailyPushLog.user_id)))
    assert int(logged or 0) == 2


@pytest.mark.asyncio
async def test_evening_reminder_targets_incomplete_daily_runs(monkeypatch) -> None:
    berlin_date = date(2026, 2, 26)
    in_progress_user_id = await _create_user("daily-push-in-progress")
    abandoned_user_id = await _create_user("daily-push-abandoned")
    completed_user_id = await _create_user("daily-push-completed")
    await _create_daily_run(
        user_id=in_progress_user_id, berlin_date=berlin_date, status="IN_PROGRESS"
    )
    await _create_daily_run(user_id=abandoned_user_id, berlin_date=berlin_date, status="ABANDONED")
    await _create_daily_run(user_id=completed_user_id, berlin_date=berlin_date, status="COMPLETED")

    bot = _DummyBot()
    monkeypatch.setattr(daily_challenge_async, "build_bot", lambda: bot)
    monkeypatch.setattr(daily_challenge_async, "datetime", _FrozenDateTime)

    result = await daily_challenge_async.run_daily_push_notifications_async(
        batch_size=100,
        push_kind="EVENING_REMINDER",
    )

    assert result["push_kind"] == "EVENING_REMINDER"
    assert int(result["sent_total"]) == 2
    assert len(bot.sent_messages) == 2
