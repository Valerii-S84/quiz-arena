from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analytics_events import EVENT_SOURCE_BOT, emit_analytics_event
from app.db.models.quiz_sessions import QuizSession
from app.db.repo.daily_runs_repo import DailyRunsRepo
from app.db.repo.purchases_repo import PurchasesRepo
from app.economy.energy.service import EnergyService
from app.economy.purchases.catalog import get_product
from app.economy.streak.service import StreakService

from .constants import DAILY_CHALLENGE_TOTAL_QUESTIONS, FRIEND_CHALLENGE_TICKET_PRODUCT_CODE

DAILY_TICKET_REWARD_SCORE = DAILY_CHALLENGE_TOTAL_QUESTIONS
DAILY_FREE_ENERGY_REWARD_BY_SCORE = {
    6: 3,
    5: 2,
}


@dataclass(frozen=True, slots=True)
class DailyAnswerState:
    daily_run_id: UUID | None
    current_question: int
    total_questions: int
    score: int
    completed: bool
    current_streak: int
    best_streak: int


def _build_daily_ticket_reward_idempotency_key(*, daily_run_id: UUID) -> str:
    return f"daily:reward:ticket:{daily_run_id}"


def _build_daily_energy_reward_idempotency_key(*, daily_run_id: UUID) -> str:
    return f"daily:reward:energy:{daily_run_id}"


def _get_purchase_service():
    from app.economy.purchases.service import PurchaseService

    return PurchaseService


async def _credit_daily_duel_ticket(
    session: AsyncSession,
    *,
    user_id: int,
    daily_run_id: UUID,
    now_utc: datetime,
) -> None:
    purchase_service = _get_purchase_service()
    purchase_idempotency_key = _build_daily_ticket_reward_idempotency_key(daily_run_id=daily_run_id)
    purchase = await PurchasesRepo.get_by_idempotency_key(session, purchase_idempotency_key)
    if purchase is None:
        product = get_product(FRIEND_CHALLENGE_TICKET_PRODUCT_CODE)
        if product is None:
            raise ValueError("friend challenge ticket product is not configured")
        purchase = purchase_service._build_purchase(
            product,
            user_id=user_id,
            idempotency_key=purchase_idempotency_key,
            discount_stars_amount=product.stars_amount,
            applied_promo_code_id=None,
            now_utc=now_utc,
        )
        await PurchasesRepo.create(session, purchase=purchase, created_at=now_utc)

    await purchase_service.apply_zero_cost_purchase(
        session,
        purchase_id=purchase.id,
        user_id=user_id,
        now_utc=now_utc,
    )


async def _apply_daily_completion_reward(
    session: AsyncSession,
    *,
    user_id: int,
    daily_run_id: UUID,
    score: int,
    now_utc: datetime,
) -> None:
    if score >= DAILY_TICKET_REWARD_SCORE:
        await _credit_daily_duel_ticket(
            session,
            user_id=user_id,
            daily_run_id=daily_run_id,
            now_utc=now_utc,
        )
        return

    free_energy_reward = DAILY_FREE_ENERGY_REWARD_BY_SCORE.get(score, 0)
    if free_energy_reward <= 0:
        return

    await EnergyService.credit_free_energy(
        session,
        user_id=user_id,
        amount=free_energy_reward,
        idempotency_key=_build_daily_energy_reward_idempotency_key(daily_run_id=daily_run_id),
        now_utc=now_utc,
        source="DAILY_CHALLENGE",
    )


async def build_daily_replay_state(
    session: AsyncSession,
    *,
    replay_session: QuizSession,
    current_streak: int,
    best_streak: int,
) -> DailyAnswerState:
    if replay_session.daily_run_id is None:
        return DailyAnswerState(
            daily_run_id=None,
            current_question=0,
            total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
            score=0,
            completed=False,
            current_streak=current_streak,
            best_streak=best_streak,
        )

    run = await DailyRunsRepo.get_by_id(session, replay_session.daily_run_id)
    if run is None:
        return DailyAnswerState(
            daily_run_id=replay_session.daily_run_id,
            current_question=0,
            total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
            score=0,
            completed=False,
            current_streak=current_streak,
            best_streak=best_streak,
        )

    return DailyAnswerState(
        daily_run_id=run.id,
        current_question=run.current_question,
        total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
        score=run.score,
        completed=run.status == "COMPLETED",
        current_streak=current_streak,
        best_streak=best_streak,
    )


async def apply_daily_answer(
    session: AsyncSession,
    *,
    user_id: int,
    quiz_session: QuizSession,
    is_correct: bool,
    now_utc: datetime,
) -> DailyAnswerState:
    if quiz_session.daily_run_id is None:
        streak_snapshot = await StreakService.sync_rollover(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )
        return DailyAnswerState(
            daily_run_id=None,
            current_question=1,
            total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
            score=1 if is_correct else 0,
            completed=False,
            current_streak=streak_snapshot.current_streak,
            best_streak=streak_snapshot.best_streak,
        )

    run = await DailyRunsRepo.get_by_id_for_update(session, quiz_session.daily_run_id)
    if run is None:
        streak_snapshot = await StreakService.sync_rollover(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )
        return DailyAnswerState(
            daily_run_id=quiz_session.daily_run_id,
            current_question=1,
            total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
            score=1 if is_correct else 0,
            completed=False,
            current_streak=streak_snapshot.current_streak,
            best_streak=streak_snapshot.best_streak,
        )

    completed_now = False
    if run.status != "COMPLETED":
        run.status = "IN_PROGRESS"
        run.completed_at = None
        run.current_question = min(DAILY_CHALLENGE_TOTAL_QUESTIONS, run.current_question + 1)
        if is_correct:
            run.score = min(DAILY_CHALLENGE_TOTAL_QUESTIONS, run.score + 1)
        if run.current_question >= DAILY_CHALLENGE_TOTAL_QUESTIONS:
            run.status = "COMPLETED"
            run.completed_at = now_utc
            completed_now = True

    if completed_now:
        await _apply_daily_completion_reward(
            session,
            user_id=user_id,
            daily_run_id=run.id,
            score=run.score,
            now_utc=now_utc,
        )
        streak_activity = await StreakService.record_activity(
            session,
            user_id=user_id,
            activity_at_utc=now_utc,
        )
        current_streak = streak_activity.current_streak
        best_streak = streak_activity.best_streak
        await emit_analytics_event(
            session,
            event_type="daily_completed",
            source=EVENT_SOURCE_BOT,
            happened_at=now_utc,
            user_id=user_id,
            payload={
                "daily_run_id": str(run.id),
                "berlin_date": run.berlin_date.isoformat(),
                "score": run.score,
                "total_questions": DAILY_CHALLENGE_TOTAL_QUESTIONS,
            },
        )
    else:
        streak_snapshot = await StreakService.sync_rollover(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )
        current_streak = streak_snapshot.current_streak
        best_streak = streak_snapshot.best_streak

    return DailyAnswerState(
        daily_run_id=run.id,
        current_question=run.current_question,
        total_questions=DAILY_CHALLENGE_TOTAL_QUESTIONS,
        score=run.score,
        completed=run.status == "COMPLETED",
        current_streak=current_streak,
        best_streak=best_streak,
    )
