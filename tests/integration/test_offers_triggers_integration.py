from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.db.models.energy_state import EnergyState
from app.db.models.offers_impressions import OfferImpression
from app.db.models.streak_state import StreakState
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.energy.constants import BERLIN_TIMEZONE
from app.economy.offers.constants import OFFER_NOT_SHOW_DISMISS_REASON, TRG_ENERGY_ZERO, TRG_LOCKED_MODE_CLICK
from app.economy.offers.service import OfferService

UTC = timezone.utc


def _berlin_date(now_utc: datetime) -> date:
    return now_utc.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date()


async def _create_user_with_state(
    *,
    seed: str,
    now_utc: datetime,
    free_energy: int,
    paid_energy: int,
    current_streak: int = 0,
    today_status: str = "NO_ACTIVITY",
    last_activity_local_date: date | None = None,
) -> int:
    async with SessionLocal.begin() as session:
        user = await UsersRepo.create(
            session,
            telegram_user_id=40_000_000_000 + (abs(hash(seed)) % 1_000_000),
            referral_code=f"O{uuid4().hex[:10]}",
            username=None,
            first_name="Offer",
            referred_by_user_id=None,
        )
        session.add(
            EnergyState(
                user_id=user.id,
                free_energy=free_energy,
                paid_energy=paid_energy,
                free_cap=20,
                regen_interval_sec=1800,
                last_regen_at=now_utc,
                last_daily_topup_local_date=_berlin_date(now_utc),
                version=0,
                updated_at=now_utc,
            )
        )
        session.add(
            StreakState(
                user_id=user.id,
                current_streak=current_streak,
                best_streak=current_streak,
                last_activity_local_date=last_activity_local_date,
                today_status=today_status,
                streak_saver_tokens=0,
                streak_saver_last_purchase_at=None,
                premium_freezes_used_week=0,
                premium_freeze_week_start_local_date=None,
                version=0,
                updated_at=now_utc,
            )
        )
        await session.flush()
        return user.id


async def _insert_offer_impression(
    *,
    user_id: int,
    now_utc: datetime,
    offer_code: str,
    trigger_code: str,
    priority: int,
    dismiss_reason: str | None = None,
    clicked_at: datetime | None = None,
) -> None:
    async with SessionLocal.begin() as session:
        session.add(
            OfferImpression(
                user_id=user_id,
                offer_code=offer_code,
                trigger_code=trigger_code,
                priority=priority,
                shown_at=now_utc,
                local_date_berlin=_berlin_date(now_utc),
                clicked_at=clicked_at,
                dismiss_reason=dismiss_reason,
                idempotency_key=f"seed:{uuid4().hex}",
            )
        )
        await session.flush()


@pytest.mark.asyncio
async def test_offer_priority_prefers_energy_zero_over_locked_mode_click() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user_with_state(
        seed="offer-priority",
        now_utc=now_utc,
        free_energy=0,
        paid_energy=0,
    )

    async with SessionLocal.begin() as session:
        selection = await OfferService.evaluate_and_log_offer(
            session,
            user_id=user_id,
            idempotency_key="offer-priority-1",
            now_utc=now_utc,
            trigger_event=TRG_LOCKED_MODE_CLICK,
        )

    assert selection is not None
    assert selection.trigger_code == TRG_ENERGY_ZERO
    assert selection.idempotent_replay is False


@pytest.mark.asyncio
async def test_offer_impression_logging_is_idempotent_by_idempotency_key() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user_with_state(
        seed="offer-idempotent",
        now_utc=now_utc,
        free_energy=0,
        paid_energy=0,
    )

    async with SessionLocal.begin() as session:
        first = await OfferService.evaluate_and_log_offer(
            session,
            user_id=user_id,
            idempotency_key="offer-idempotent-key",
            now_utc=now_utc,
        )
        second = await OfferService.evaluate_and_log_offer(
            session,
            user_id=user_id,
            idempotency_key="offer-idempotent-key",
            now_utc=now_utc,
        )

    assert first is not None
    assert second is not None
    assert first.impression_id == second.impression_id
    assert first.idempotent_replay is False
    assert second.idempotent_replay is True

    async with SessionLocal.begin() as session:
        stmt = select(func.count(OfferImpression.id)).where(OfferImpression.user_id == user_id)
        assert int(await session.scalar(stmt) or 0) == 1


@pytest.mark.asyncio
async def test_offer_blocking_modal_cap_blocks_new_blocking_offer_for_6h() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user_with_state(
        seed="offer-cap-6h",
        now_utc=now_utc,
        free_energy=0,
        paid_energy=0,
    )
    await _insert_offer_impression(
        user_id=user_id,
        now_utc=now_utc.replace(hour=11),
        offer_code="OFFER_LOCKED_MODE_MEGA",
        trigger_code=TRG_LOCKED_MODE_CLICK,
        priority=90,
    )

    async with SessionLocal.begin() as session:
        selection = await OfferService.evaluate_and_log_offer(
            session,
            user_id=user_id,
            idempotency_key="offer-cap-6h-check",
            now_utc=now_utc,
        )

    assert selection is None


@pytest.mark.asyncio
async def test_offer_daily_cap_blocks_after_three_impressions() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user_with_state(
        seed="offer-cap-daily",
        now_utc=now_utc,
        free_energy=0,
        paid_energy=0,
    )
    for hour in (8, 9, 10):
        await _insert_offer_impression(
            user_id=user_id,
            now_utc=now_utc.replace(hour=hour),
            offer_code=f"OFFER_SEEDED_{hour}",
            trigger_code=f"TRG_SEEDED_{hour}",
            priority=10,
        )

    async with SessionLocal.begin() as session:
        selection = await OfferService.evaluate_and_log_offer(
            session,
            user_id=user_id,
            idempotency_key="offer-cap-daily-check",
            now_utc=now_utc,
        )

    assert selection is None


@pytest.mark.asyncio
async def test_offer_repeat_cap_blocks_same_offer_within_24h() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user_with_state(
        seed="offer-cap-repeat",
        now_utc=now_utc,
        free_energy=0,
        paid_energy=0,
    )
    await _insert_offer_impression(
        user_id=user_id,
        now_utc=now_utc.replace(hour=2),
        offer_code="OFFER_ENERGY_ZERO",
        trigger_code=TRG_ENERGY_ZERO,
        priority=100,
    )

    async with SessionLocal.begin() as session:
        selection = await OfferService.evaluate_and_log_offer(
            session,
            user_id=user_id,
            idempotency_key="offer-cap-repeat-check",
            now_utc=now_utc,
        )

    assert selection is None


@pytest.mark.asyncio
async def test_offer_mute_window_blocks_offer_for_72h_after_not_show() -> None:
    now_utc = datetime(2026, 2, 18, 12, 0, tzinfo=UTC)
    user_id = await _create_user_with_state(
        seed="offer-cap-mute",
        now_utc=now_utc,
        free_energy=0,
        paid_energy=0,
    )
    await _insert_offer_impression(
        user_id=user_id,
        now_utc=now_utc.replace(hour=10),
        offer_code="OFFER_ENERGY_ZERO",
        trigger_code=TRG_ENERGY_ZERO,
        priority=100,
        dismiss_reason=OFFER_NOT_SHOW_DISMISS_REASON,
        clicked_at=now_utc.replace(hour=11),
    )

    async with SessionLocal.begin() as session:
        selection = await OfferService.evaluate_and_log_offer(
            session,
            user_id=user_id,
            idempotency_key="offer-cap-mute-check",
            now_utc=now_utc,
        )

    assert selection is None
