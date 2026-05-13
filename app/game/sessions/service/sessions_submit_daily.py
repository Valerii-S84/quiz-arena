from __future__ import annotations

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

from .constants import DAILY_CHALLENGE_TOTAL_QUESTIONS
from .sessions_submit_daily_progress import advance_daily_run
from .sessions_submit_daily_replay_state import build_daily_replay_state_impl
from .sessions_submit_daily_rewards import DailyTicketRewardDeps, credit_daily_duel_ticket
from .sessions_submit_daily_state import (
    DailyAnswerState,
    build_existing_daily_run_state,
    build_missing_daily_run_state,
)

DAILY_TICKET_REWARD_SCORE = DAILY_CHALLENGE_TOTAL_QUESTIONS
DAILY_FREE_ENERGY_REWARD_BY_SCORE = {
    6: 3,
    5: 2,
}


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
    await credit_daily_duel_ticket(
        session,
        user_id=user_id,
        daily_run_id=daily_run_id,
        now_utc=now_utc,
        deps=DailyTicketRewardDeps(
            purchase_service_factory=_get_purchase_service,
            product_lookup=get_product,
            purchases_repo=PurchasesRepo,
            idempotency_key_builder=_build_daily_ticket_reward_idempotency_key,
        ),
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
    return await build_daily_replay_state_impl(
        session,
        replay_session=replay_session,
        current_streak=current_streak,
        best_streak=best_streak,
        daily_runs_repo=DailyRunsRepo,
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
        return await _build_missing_daily_answer_state(
            session,
            daily_run_id=None,
            user_id=user_id,
            is_correct=is_correct,
            now_utc=now_utc,
        )

    run = await DailyRunsRepo.get_by_id_for_update(session, quiz_session.daily_run_id)
    if run is None:
        return await _build_missing_daily_answer_state(
            session,
            daily_run_id=quiz_session.daily_run_id,
            user_id=user_id,
            is_correct=is_correct,
            now_utc=now_utc,
        )

    if advance_daily_run(run, is_correct=is_correct, now_utc=now_utc):
        streak = await _record_daily_completion(
            session,
            user_id=user_id,
            run=run,
            now_utc=now_utc,
        )
    else:
        streak = await StreakService.sync_rollover(
            session,
            user_id=user_id,
            now_utc=now_utc,
        )

    return build_existing_daily_run_state(
        run=run,
        current_streak=streak.current_streak,
        best_streak=streak.best_streak,
    )


async def _build_missing_daily_answer_state(
    session: AsyncSession,
    *,
    daily_run_id: UUID | None,
    user_id: int,
    is_correct: bool,
    now_utc: datetime,
) -> DailyAnswerState:
    streak = await StreakService.sync_rollover(session, user_id=user_id, now_utc=now_utc)
    return build_missing_daily_run_state(
        daily_run_id=daily_run_id,
        is_correct=is_correct,
        current_streak=streak.current_streak,
        best_streak=streak.best_streak,
    )


async def _record_daily_completion(
    session: AsyncSession,
    *,
    user_id: int,
    run,
    now_utc: datetime,
):
    await _apply_daily_completion_reward(
        session,
        user_id=user_id,
        daily_run_id=run.id,
        score=run.score,
        now_utc=now_utc,
    )
    streak = await StreakService.record_activity(
        session,
        user_id=user_id,
        activity_at_utc=now_utc,
    )
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
    return streak
