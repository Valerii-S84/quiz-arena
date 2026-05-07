from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.db.models.entitlements import Entitlement
from app.db.session import SessionLocal
from app.game.arena_duels.errors import ArenaDuelPaymentRequiredError
from app.game.duels.limits import DuelLimitService
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
            raw_successful_payment={
                "invoice_payload": init.invoice_payload,
                "currency": "XTR",
                "total_amount": init.final_stars_amount,
            },
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
async def test_friend_challenge_purchase_requires_successful_payment_before_ticket_access() -> None:
    now_utc = datetime(2026, 2, 19, 21, 0, tzinfo=UTC)
    creator_user_id = await _create_user("fc_limit_unpaid_ticket_regression")

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

        init = await PurchaseService.init_purchase(
            session,
            user_id=creator_user_id,
            product_code="FRIEND_CHALLENGE_5",
            idempotency_key="buy:friend_challenge_ticket:unpaid-regression",
            now_utc=now_utc + timedelta(minutes=2),
        )

        with pytest.raises(FriendChallengePaymentRequiredError):
            await GameSessionService.create_friend_challenge(
                session,
                creator_user_id=creator_user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=now_utc + timedelta(minutes=3),
            )

        await PurchaseService.mark_invoice_sent(session, purchase_id=init.purchase_id)

        with pytest.raises(FriendChallengePaymentRequiredError):
            await GameSessionService.create_friend_challenge(
                session,
                creator_user_id=creator_user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=now_utc + timedelta(minutes=4),
            )

        await PurchaseService.validate_precheckout(
            session,
            user_id=creator_user_id,
            invoice_payload=init.invoice_payload,
            total_amount=init.final_stars_amount,
            precheckout_query_id="pre-fc-unpaid-regression",
        )

        with pytest.raises(FriendChallengePaymentRequiredError):
            await GameSessionService.create_friend_challenge(
                session,
                creator_user_id=creator_user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=now_utc + timedelta(minutes=5),
            )

        await PurchaseService.apply_successful_payment(
            session,
            user_id=creator_user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id=f"tg_fc_ticket_{uuid4().hex}",
            raw_successful_payment={
                "invoice_payload": init.invoice_payload,
                "currency": "XTR",
                "total_amount": init.final_stars_amount,
            },
            now_utc=now_utc + timedelta(minutes=6),
        )

        paid_challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=7),
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


@pytest.mark.asyncio
async def test_tournament_duels_do_not_consume_free_friend_challenge_quota() -> None:
    now_utc = datetime(2026, 2, 19, 20, 30, tzinfo=UTC)
    creator_user_id = await _create_user("fc_limit_creator_tournament")
    opponent_user_id = await _create_user("fc_limit_opponent_tournament")

    async with SessionLocal.begin() as session:
        await GameSessionService.create_tournament_match_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            opponent_user_id=opponent_user_id,
            mode_code="QUICK_MIX_A1A2",
            total_rounds=7,
            tournament_match_id=uuid4(),
            now_utc=now_utc,
        )
        await GameSessionService.create_tournament_match_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            opponent_user_id=opponent_user_id,
            mode_code="QUICK_MIX_A1A2",
            total_rounds=7,
            tournament_match_id=uuid4(),
            now_utc=now_utc + timedelta(minutes=1),
        )

        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=2),
        )

        assert challenge.access_type == "FREE"


@pytest.mark.asyncio
async def test_friend_challenge_free_quota_resets_on_new_berlin_day() -> None:
    creator_user_id = await _create_user("fc_limit_berlin_midnight_reset")
    late_berlin_day_utc = datetime(2026, 1, 15, 22, 57, tzinfo=UTC)
    new_berlin_day_utc = datetime(2026, 1, 15, 23, 1, tzinfo=UTC)

    async with SessionLocal.begin() as session:
        first = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=late_berlin_day_utc,
        )
        second = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=late_berlin_day_utc + timedelta(minutes=1),
        )
        assert first.access_type == "FREE"
        assert second.access_type == "FREE"

        with pytest.raises(FriendChallengePaymentRequiredError):
            await GameSessionService.create_friend_challenge(
                session,
                creator_user_id=creator_user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=late_berlin_day_utc + timedelta(minutes=2),
            )

        reset_day_first = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=new_berlin_day_utc,
        )

        assert reset_day_first.access_type == "FREE"


@pytest.mark.asyncio
async def test_friend_challenge_free_quota_persists_across_early_berlin_hours() -> None:
    creator_user_id = await _create_user("fc_limit_berlin_early_hours")
    berlin_day_start_utc = datetime(2026, 1, 15, 23, 5, tzinfo=UTC)

    async with SessionLocal.begin() as session:
        first = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=berlin_day_start_utc,
        )
        second = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=berlin_day_start_utc + timedelta(minutes=70),
        )
        assert first.access_type == "FREE"
        assert second.access_type == "FREE"

        with pytest.raises(FriendChallengePaymentRequiredError):
            await GameSessionService.create_friend_challenge(
                session,
                creator_user_id=creator_user_id,
                mode_code="QUICK_MIX_A1A2",
                now_utc=berlin_day_start_utc + timedelta(minutes=114),
            )


@pytest.mark.asyncio
async def test_paid_ticket_used_in_friend_flow_is_not_reusable_for_arena() -> None:
    now_utc = datetime(2026, 2, 20, 10, 0, tzinfo=UTC)
    creator_user_id = await _create_user("fc_limit_cross_mode_ticket_consumption")
    from app.game.arena_duels.service_baseline_start import create_arena_duel_baseline

    async with SessionLocal.begin() as session:
        init = await PurchaseService.init_purchase(
            session,
            user_id=creator_user_id,
            product_code="FRIEND_CHALLENGE_5",
            idempotency_key="buy:friend_challenge_ticket:cross-mode",
            now_utc=now_utc,
        )
        await PurchaseService.apply_successful_payment(
            session,
            user_id=creator_user_id,
            invoice_payload=init.invoice_payload,
            telegram_payment_charge_id=f"tg_fc_cross_mode_{uuid4().hex}",
            raw_successful_payment={
                "invoice_payload": init.invoice_payload,
                "currency": "XTR",
                "total_amount": init.final_stars_amount,
            },
            now_utc=now_utc + timedelta(minutes=1),
        )

        await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=2),
        )
        await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=3),
        )
        paid_friend_challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=4),
        )
        assert paid_friend_challenge.access_type == "PAID_TICKET"

        arena_free_access = await DuelLimitService.resolve_arena_create_access_type(
            session,
            user_id=creator_user_id,
            now_utc=now_utc + timedelta(minutes=5),
        )
        assert arena_free_access == "FREE"

        await create_arena_duel_baseline(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc + timedelta(minutes=5),
            access_type=arena_free_access,
        )

        with pytest.raises(ArenaDuelPaymentRequiredError):
            await DuelLimitService.resolve_arena_create_access_type(
                session,
                user_id=creator_user_id,
                now_utc=now_utc + timedelta(minutes=6),
            )
