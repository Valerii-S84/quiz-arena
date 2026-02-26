from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.db.models.referrals import Referral
from app.db.session import SessionLocal
from app.workers.tasks import referrals as referrals_task
from app.workers.tasks import referrals_notifications
from tests.integration.referrals_fixtures import UTC, _create_referral_row, _create_user


class _FrozenDateTime(datetime):
    current = datetime(2026, 2, 26, 12, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        base = cls.current
        if tz is None:
            return base.replace(tzinfo=None)
        return base.astimezone(tz)


class _DummyBotSession:
    async def close(self) -> None:
        return None


class _DummyBot:
    def __init__(self) -> None:
        self.session = _DummyBotSession()
        self.sent_messages: list[int] = []

    async def send_message(self, *, chat_id: int, text: str, reply_markup) -> None:
        del text, reply_markup
        self.sent_messages.append(chat_id)


@pytest.mark.asyncio
async def test_referral_reward_notification_sent_once(monkeypatch) -> None:
    now_utc = datetime(2026, 2, 26, 12, 0, tzinfo=UTC)
    referrer = await _create_user("referrer-reward-notified-once")
    referred_users = [await _create_user(f"referred-reward-notified-{idx}") for idx in range(3)]

    for referred in referred_users:
        await _create_referral_row(
            referrer_user_id=referrer.id,
            referred_user_id=referred.id,
            referral_code=referrer.referral_code,
            status="QUALIFIED",
            created_at=now_utc - timedelta(days=5),
            qualified_at=now_utc - timedelta(hours=49),
        )

    bot = _DummyBot()
    monkeypatch.setattr(referrals_notifications, "build_bot", lambda: bot)
    monkeypatch.setattr(referrals_task, "datetime", _FrozenDateTime)

    async def _fake_send_ops_alert(*, event: str, payload: dict[str, object]) -> bool:
        del event, payload
        return False

    monkeypatch.setattr(referrals_task, "send_ops_alert", _fake_send_ops_alert)

    _FrozenDateTime.current = now_utc
    first = await referrals_task.run_referral_reward_distribution_async(batch_size=200)
    _FrozenDateTime.current = now_utc + timedelta(minutes=15)
    second = await referrals_task.run_referral_reward_distribution_async(batch_size=200)

    assert int(first["reward_user_notified"]) == 1
    assert int(second["reward_user_notified"]) == 0
    assert bot.sent_messages.count(int(referrer.telegram_user_id)) == 1

    async with SessionLocal.begin() as session:
        notified_count = int(
            await session.scalar(
                select(func.count(Referral.id)).where(
                    Referral.referrer_user_id == referrer.id,
                    Referral.notified_at.is_not(None),
                )
            )
            or 0
        )
    assert notified_count == 1
