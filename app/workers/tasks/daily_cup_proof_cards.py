from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog

from app.bot.application import build_bot
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import DAILY_CUP_TOURNAMENT_TYPES, TOURNAMENT_STATUS_COMPLETED
from app.game.tournaments.daily_cup_standings import calculate_daily_cup_standings
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks import daily_cup_proof_cards_runtime
from app.workers.tasks.daily_cup_config import DAILY_CUP_TIMEZONE
from app.workers.tasks.daily_cup_proof_card_sender import send_daily_cup_proof_card
from app.workers.tasks.daily_cup_proof_cards_context import load_daily_cup_proof_cards_context
from app.workers.tasks.daily_cup_proof_cards_delivery import deliver_daily_cup_proof_cards
from app.workers.tasks.daily_cup_proof_cards_enqueue import enqueue_daily_cup_proof_cards_job
from app.workers.tasks.daily_cup_proof_cards_text import format_points, format_user_label
from app.workers.tasks.daily_cup_task_helpers import is_celery_task, is_today_daily_cup_tournament
from app.workers.tasks.daily_cup_winner_rewards import (
    DAILY_CUP_REWARD_MIN_PARTICIPANTS,
    grant_daily_cup_winner_rewards,
    send_daily_cup_winner_reward_messages,
)
from app.workers.tasks.tournaments_proof_card_render import render_tournament_proof_card_png

logger = structlog.get_logger("app.workers.tasks.daily_cup_proof_cards")
_empty_result = daily_cup_proof_cards_runtime.empty_daily_cup_proof_cards_result


async def _load_proof_cards_context(
    *,
    parsed_tournament_id: UUID,
    user_id: int | None,
    now_utc: datetime,
) -> Any:
    return await daily_cup_proof_cards_runtime.load_daily_cup_proof_cards_runtime_context(
        parsed_tournament_id=parsed_tournament_id,
        user_id=user_id,
        now_utc=now_utc,
        logger=logger,
        session_factory=SessionLocal,
        load_context_fn=load_daily_cup_proof_cards_context,
        tournaments_repo=TournamentsRepo,
        users_repo=UsersRepo,
        matches_repo=TournamentMatchesRepo,
        calculate_standings_fn=calculate_daily_cup_standings,
        format_points_fn=format_points,
        format_user_label_fn=format_user_label,
        is_today_daily_cup_tournament_fn=is_today_daily_cup_tournament,
        daily_cup_tournament_types=DAILY_CUP_TOURNAMENT_TYPES,
        tournament_completed_status=TOURNAMENT_STATUS_COMPLETED,
        timezone_name=DAILY_CUP_TIMEZONE,
    )


async def _grant_winner_rewards_once(
    *,
    bot: Any,
    context: Any,
    tournament_id: str,
    now_utc: datetime,
) -> list[Any]:
    return await daily_cup_proof_cards_runtime.grant_daily_cup_winner_rewards_once(
        bot=bot,
        context=context,
        tournament_id=tournament_id,
        now_utc=now_utc,
        logger=logger,
        session_factory=SessionLocal,
        tournaments_repo=TournamentsRepo,
        grant_winner_rewards_fn=grant_daily_cup_winner_rewards,
        send_reward_messages_fn=send_daily_cup_winner_reward_messages,
    )


async def run_daily_cup_proof_cards_async(
    *,
    tournament_id: str,
    user_id: int | None = None,
    initial_delay_seconds: int = 2,
) -> dict[str, int]:
    try:
        parsed_tournament_id = UUID(tournament_id)
    except ValueError:
        return _empty_result()

    now_utc = datetime.now(timezone.utc)
    context = await _load_proof_cards_context(
        parsed_tournament_id=parsed_tournament_id,
        user_id=user_id,
        now_utc=now_utc,
    )
    if context is None:
        return _empty_result()
    if not context.participants:
        return {**_empty_result(), "processed": 1}

    if initial_delay_seconds > 0:
        await asyncio.sleep(max(0, int(initial_delay_seconds)))

    bot = build_bot()
    try:
        delivery = await deliver_daily_cup_proof_cards(
            context=context,
            bot=bot,
            tournament_id=tournament_id,
            now_utc=now_utc,
            session_factory=SessionLocal,
            participants_repo=TournamentParticipantsRepo,
            send_proof_card_fn=send_daily_cup_proof_card,
            render_card_png=render_tournament_proof_card_png,
            logger=logger,
        )

        if user_id is None and context.participants_total >= DAILY_CUP_REWARD_MIN_PARTICIPANTS:
            await _grant_winner_rewards_once(
                bot=bot,
                context=context,
                tournament_id=tournament_id,
                now_utc=now_utc,
            )
    finally:
        await bot.session.close()

    return {
        "processed": 1,
        "participants_total": context.participants_total,
        "sent": delivery.sent,
        "cached_reused": delivery.cached_reused,
        "failed": delivery.failed,
    }


def enqueue_daily_cup_proof_cards(
    *,
    tournament_id: str,
    user_id: int | None = None,
    delay_seconds: int = 2,
) -> None:
    enqueue_daily_cup_proof_cards_job(
        tournament_id=tournament_id,
        user_id=user_id,
        delay_seconds=delay_seconds,
        celery_task=run_daily_cup_proof_cards,
        async_fn=run_daily_cup_proof_cards_async,
        is_celery_task_fn=is_celery_task,
        run_async_job_fn=run_async_job,
        logger=logger,
    )


@celery_app.task(name="app.workers.tasks.daily_cup.run_daily_cup_proof_cards")
def run_daily_cup_proof_cards(
    *,
    tournament_id: str,
    user_id: int | None = None,
    initial_delay_seconds: int = 2,
) -> dict[str, int]:
    return run_async_job(
        run_daily_cup_proof_cards_async(
            tournament_id=tournament_id,
            user_id=user_id,
            initial_delay_seconds=initial_delay_seconds,
        )
    )
