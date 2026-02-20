from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.analytics_events import AnalyticsEvent
from app.db.repo.energy_repo import EnergyRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.energy.service import EnergyService
from app.economy.energy.time import berlin_local_date
from app.economy.purchases.service import PurchaseService
from app.economy.streak.service import StreakService

UTC = timezone.utc


async def _create_user(seed: str) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=81_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"E{uuid4().hex[:10].upper()}",
            username=None,
            first_name="AnalyticsEvents",
            referred_by_user_id=None,
        )
        return int(user.id)


async def _list_user_events(user_id: int, *, event_type: str) -> list[AnalyticsEvent]:
    async with SessionLocal.begin() as session:
        result = await session.execute(
            select(AnalyticsEvent)
            .where(
                AnalyticsEvent.user_id == user_id,
                AnalyticsEvent.event_type == event_type,
            )
            .order_by(AnalyticsEvent.happened_at.asc(), AnalyticsEvent.id.asc())
        )
        return list(result.scalars().all())


@pytest.mark.asyncio
async def test_purchase_flow_emits_key_funnel_events() -> None:
    user_id = await _create_user("purchase-funnel")
    now_utc = datetime.now(UTC)

    async with SessionLocal.begin() as session:
        init_result = await PurchaseService.init_purchase(
            session,
            user_id=user_id,
            product_code="ENERGY_10",
            idempotency_key="analytics-funnel:init",
            now_utc=now_utc,
        )

    async with SessionLocal.begin() as session:
        await PurchaseService.mark_invoice_sent(
            session,
            purchase_id=init_result.purchase_id,
        )

    async with SessionLocal.begin() as session:
        await PurchaseService.validate_precheckout(
            session,
            user_id=user_id,
            invoice_payload=init_result.invoice_payload,
            total_amount=init_result.final_stars_amount,
            now_utc=now_utc + timedelta(minutes=1),
        )

    async with SessionLocal.begin() as session:
        await PurchaseService.apply_successful_payment(
            session,
            user_id=user_id,
            invoice_payload=init_result.invoice_payload,
            telegram_payment_charge_id=f"tg_charge_{uuid4().hex}",
            raw_successful_payment={"invoice_payload": init_result.invoice_payload},
            now_utc=now_utc + timedelta(minutes=2),
        )

    init_events = await _list_user_events(user_id, event_type="purchase_init_created")
    invoice_events = await _list_user_events(user_id, event_type="purchase_invoice_sent")
    precheckout_events = await _list_user_events(user_id, event_type="purchase_precheckout_ok")
    paid_events = await _list_user_events(user_id, event_type="purchase_paid_uncredited")
    credited_events = await _list_user_events(user_id, event_type="purchase_credited")

    assert len(init_events) == 1
    assert len(invoice_events) == 1
    assert len(precheckout_events) == 1
    assert len(paid_events) == 1
    assert len(credited_events) == 1


@pytest.mark.asyncio
async def test_energy_depletion_emits_gameplay_energy_zero_event() -> None:
    user_id = await _create_user("energy-zero")
    now_utc = datetime.now(UTC)

    async with SessionLocal.begin() as session:
        await EnergyService.initialize_user_state(session, user_id=user_id, now_utc=now_utc)
        state = await EnergyRepo.get_by_user_id_for_update(session, user_id)
        assert state is not None
        state.free_energy = 1
        state.paid_energy = 0
        state.last_regen_at = now_utc
        state.last_daily_topup_local_date = berlin_local_date(now_utc)
        state.updated_at = now_utc

        result = await EnergyService.consume_quiz(
            session,
            user_id=user_id,
            idempotency_key="analytics-energy-zero:1",
            now_utc=now_utc + timedelta(seconds=1),
        )
        assert result.allowed is True

    events = await _list_user_events(user_id, event_type="gameplay_energy_zero")
    assert len(events) == 1
    assert events[0].payload.get("after_state") == "E_EMPTY"


@pytest.mark.asyncio
async def test_streak_rollover_emits_streak_lost_event() -> None:
    user_id = await _create_user("streak-lost")
    now_utc = datetime.now(UTC)
    old_activity_utc = now_utc - timedelta(days=3)

    async with SessionLocal.begin() as session:
        result = await StreakService.record_activity(
            session,
            user_id=user_id,
            activity_at_utc=old_activity_utc,
        )
        assert result.current_streak >= 1

    async with SessionLocal.begin() as session:
        await StreakService.sync_rollover(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )

    events = await _list_user_events(user_id, event_type="streak_lost")
    assert len(events) == 1
    assert int(events[0].payload.get("previous_streak", 0)) >= 1
