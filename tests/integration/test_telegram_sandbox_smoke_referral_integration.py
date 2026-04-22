from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db.models.entitlements import Entitlement
from app.db.models.ledger_entries import LedgerEntry
from app.db.models.referrals import Referral
from app.db.session import SessionLocal
from app.economy.referrals.service import ReferralService
from app.main import app
from tests.integration.telegram_sandbox_smoke_bot import _BotApiStub, _configure_webhook_processing
from tests.integration.telegram_sandbox_smoke_fixtures import (
    UTC,
    _callback_update,
    _create_user,
    _post_webhook_update,
)


@pytest.mark.asyncio
async def test_telegram_webhook_smoke_referral_reward_choice_duplicate_replay(
    monkeypatch,
) -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    referrer = await _create_user(telegram_user_id=90_000_000_101, first_name="Referrer")
    referred_users = [
        await _create_user(telegram_user_id=90_000_000_110 + idx, first_name=f"Referred{idx}")
        for idx in range(3)
    ]

    async with SessionLocal.begin() as session:
        for referred in referred_users:
            session.add(
                Referral(
                    referrer_user_id=referrer.id,
                    referred_user_id=referred.id,
                    referral_code=referrer.referral_code,
                    status="QUALIFIED",
                    qualified_at=now_utc - timedelta(hours=49),
                    rewarded_at=None,
                    fraud_score=0,
                    created_at=now_utc - timedelta(days=5),
                )
            )

    async with SessionLocal.begin() as session:
        distribution = await ReferralService.run_reward_distribution(
            session,
            now_utc=now_utc,
            reward_code=None,
        )
        assert distribution["awaiting_choice"] == 1

    bot_api = _BotApiStub()
    queue = _configure_webhook_processing(monkeypatch, bot_api)

    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 8080)),
        base_url="http://testserver",
    ) as client:
        await _post_webhook_update(
            client,
            _callback_update(
                update_id=1_010_001,
                telegram_user_id=referrer.telegram_user_id,
                callback_query_id="cb-ref-reward-1",
                data="referral:reward:PREMIUM_STARTER",
            ),
        )
        await queue.drain()

        await _post_webhook_update(
            client,
            _callback_update(
                update_id=1_010_002,
                telegram_user_id=referrer.telegram_user_id,
                callback_query_id="cb-ref-reward-dup-1",
                data="referral:reward:PREMIUM_STARTER",
            ),
        )
        await queue.drain()

    async with SessionLocal.begin() as session:
        rewarded_count = await session.scalar(
            select(func.count(Referral.id)).where(
                Referral.referrer_user_id == referrer.id,
                Referral.status == "REWARDED",
            )
        )
        assert int(rewarded_count or 0) == 1

        active_premium = await session.scalar(
            select(func.count(Entitlement.id)).where(
                Entitlement.user_id == referrer.id,
                Entitlement.entitlement_type == "PREMIUM",
                Entitlement.status == "ACTIVE",
            )
        )
        assert int(active_premium or 0) == 1

        reward_credit_count = await session.scalar(
            select(func.count(LedgerEntry.id)).where(
                LedgerEntry.user_id == referrer.id,
                LedgerEntry.entry_type == "REFERRAL_REWARD",
                LedgerEntry.asset == "PREMIUM",
                LedgerEntry.source == "REFERRAL",
            )
        )
        assert int(reward_credit_count or 0) == 1
