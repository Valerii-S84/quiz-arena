from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.db.models.entitlements import Entitlement
from app.db.session import SessionLocal
from app.economy.purchases.service import PurchaseService
from app.game.sessions.errors import FriendChallengePaymentRequiredError
from app.game.sessions.service import GameSessionService
from tests.integration.friend_challenge_fixtures import UTC, _create_user


@pytest.mark.asyncio
async def test_friend_challenge_allows_two_free_then_requires_paid_ticket() -> None:
    now_utc = datetime(2026, 2, 19, 19, 30, tzinfo=UTC)
    creator_user_id = await _create_user("fc_limit_creator")

    async with SessionLocal.begin() as session:
        first = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
        )
        second = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=1),
        )
        assert first.access_type == "FREE"
        assert second.access_type == "FREE"

        with pytest.raises(FriendChallengePaymentRequiredError):
            await GameSessionService.create_friend_challenge(
                session,
                creator_user_id=creator_user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=now_utc + timedelta(minutes=2),
            )

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=creator_user_id,
            product_code="FRIEND_CHALLENGE_5",
            idempotency_key="buy:friend_challenge_ticket:test",
            now_utc=now_utc + timedelta(minutes=3),
        )
        await PurchaseService.apply_successful_payment(
            session,
            user_id=creator_user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id=f"tg_fc_ticket_{uuid4().hex}",
            raw_successful_payment={"invoice_payload": init.invoice_payload},
            now_utc=now_utc + timedelta(minutes=4),
        )

        paid_challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=5),
        )
        assert paid_challenge.access_type == "PAID_TICKET"


@pytest.mark.asyncio
async def test_friend_challenge_premium_is_unlimited() -> None:
    now_utc = datetime(2026, 2, 19, 20, 0, tzinfo=UTC)
    creator_user_id = await _create_user("fc_premium_creator")

    async with SessionLocal.begin() as session:
        session.add(
            Entitlement(
                user_id=creator_user_id,
                entitlement_type="PREMIUM",
                scope="PREMIUM_MONTH",
                status="ACTIVE",
                starts_at=now_utc - timedelta(minutes=1),
                ends_at=now_utc + timedelta(days=30),
                source_purchase_id=None,
                idempotency_key=f"test:fc:premium:{uuid4().hex}",
                metadata_={},
                created_at=now_utc,
                updated_at=now_utc,
            )
        )
        await session.flush()

        access_types: list[str] = []
        for idx in range(1, 6):
            challenge = await GameSessionService.create_friend_challenge(
                session,
                creator_user_id=creator_user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=now_utc + timedelta(minutes=idx),
            )
            access_types.append(challenge.access_type)

        assert access_types == ["PREMIUM", "PREMIUM", "PREMIUM", "PREMIUM", "PREMIUM"]
