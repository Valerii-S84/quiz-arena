from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models.analytics_events import AnalyticsEvent
from app.db.repo.energy_repo import EnergyRepo
from app.db.repo.quiz_sessions_repo import QuizSessionsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.economy.energy.service import EnergyService
from app.economy.energy.time import berlin_local_date
from app.economy.purchases.service import PurchaseService
from app.economy.streak.service import StreakService
from app.game.questions.runtime_bank import get_question_by_id
from app.game.sessions.service import GameSessionService

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


@pytest.mark.asyncio
async def test_friend_challenge_flow_emits_created_joined_completed_and_rematch_events() -> None:
    creator_user_id = await _create_user("fc-events-creator")
    opponent_user_id = await _create_user("fc-events-opponent")
    now_utc = datetime.now(UTC)

    async with SessionLocal.begin() as session:
        challenge = await GameSessionService.create_friend_challenge(
            session,
            creator_user_id=creator_user_id,
            mode_code="QUICK_MIX_A1A2",
            now_utc=now_utc,
            total_rounds=1,
        )
        await GameSessionService.join_friend_challenge_by_token(
            session,
            user_id=opponent_user_id,
            invite_token=challenge.invite_token,
            now_utc=now_utc + timedelta(seconds=1),
        )
        creator_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc-events:creator:start",
            now_utc=now_utc + timedelta(seconds=2),
        )
        opponent_round = await GameSessionService.start_friend_challenge_round(
            session,
            user_id=opponent_user_id,
            challenge_id=challenge.challenge_id,
            idempotency_key="fc-events:opponent:start",
            now_utc=now_utc + timedelta(seconds=3),
        )
        assert creator_round.start_result is not None
        assert opponent_round.start_result is not None

        creator_session = await QuizSessionsRepo.get_by_id(session, creator_round.start_result.session.session_id)
        assert creator_session is not None
        question = await get_question_by_id(
            session,
            creator_session.mode_code,
            question_id=creator_session.question_id or "",
            local_date_berlin=creator_session.local_date_berlin,
        )
        assert question is not None

        await GameSessionService.submit_answer(
            session,
            user_id=creator_user_id,
            session_id=creator_round.start_result.session.session_id,
            selected_option=question.correct_option,
            idempotency_key="fc-events:creator:answer",
            now_utc=now_utc + timedelta(seconds=4),
        )
        await GameSessionService.submit_answer(
            session,
            user_id=opponent_user_id,
            session_id=opponent_round.start_result.session.session_id,
            selected_option=(question.correct_option + 1) % 4,
            idempotency_key="fc-events:opponent:answer",
            now_utc=now_utc + timedelta(seconds=5),
        )
        await GameSessionService.create_friend_challenge_rematch(
            session,
            initiator_user_id=creator_user_id,
            challenge_id=challenge.challenge_id,
            now_utc=now_utc + timedelta(seconds=6),
        )

    creator_created = await _list_user_events(creator_user_id, event_type="friend_challenge_created")
    opponent_joined = await _list_user_events(opponent_user_id, event_type="friend_challenge_joined")
    opponent_completed = await _list_user_events(opponent_user_id, event_type="friend_challenge_completed")
    creator_rematch = await _list_user_events(creator_user_id, event_type="friend_challenge_rematch_created")

    assert len(creator_created) >= 2
    assert len(opponent_joined) == 1
    assert len(opponent_completed) == 1
    assert len(creator_rematch) == 1
