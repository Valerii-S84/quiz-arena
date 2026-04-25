from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import structlog

from app.bot.application import build_bot
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.session import SessionLocal
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.daily_cup_proof_card_sender import send_daily_cup_proof_card
from app.workers.tasks.daily_cup_proof_cards_delivery import deliver_daily_cup_proof_cards
from app.workers.tasks.daily_cup_proof_cards_runtime import (
    empty_daily_cup_proof_cards_result,
    grant_daily_cup_winner_rewards_once,
    load_daily_cup_proof_cards_runtime_context,
)
from app.workers.tasks.daily_cup_task_helpers import is_celery_task
from app.workers.tasks.daily_cup_winner_rewards import DAILY_CUP_REWARD_MIN_PARTICIPANTS
from app.workers.tasks.tournaments_proof_card_render import render_tournament_proof_card_png

logger = structlog.get_logger("app.workers.tasks.daily_cup_proof_cards")


async def run_daily_cup_proof_cards_async(
    *,
    tournament_id: str,
    user_id: int | None = None,
    initial_delay_seconds: int = 2,
) -> dict[str, int]:
    try:
        parsed_tournament_id = UUID(tournament_id)
    except ValueError:
        return empty_daily_cup_proof_cards_result()

    now_utc = datetime.now(timezone.utc)
    context = await load_daily_cup_proof_cards_runtime_context(
        parsed_tournament_id=parsed_tournament_id,
        user_id=user_id,
        now_utc=now_utc,
        logger=logger,
    )
    if context is None:
        return empty_daily_cup_proof_cards_result()
    if not context.participants:
        return {**empty_daily_cup_proof_cards_result(), "processed": 1}

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
            await grant_daily_cup_winner_rewards_once(
                bot=bot,
                context=context,
                tournament_id=tournament_id,
                now_utc=now_utc,
                logger=logger,
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
    try:
        if is_celery_task(run_daily_cup_proof_cards):
            run_daily_cup_proof_cards.apply_async(
                kwargs={
                    "tournament_id": tournament_id,
                    "user_id": user_id,
                    "initial_delay_seconds": 0,
                },
                countdown=max(0, int(delay_seconds)),
            )
            return
        run_async_job(
            run_daily_cup_proof_cards_async(
                tournament_id=tournament_id,
                user_id=user_id,
                initial_delay_seconds=max(0, int(delay_seconds)),
            )
        )
    except Exception as exc:
        logger.warning(
            "daily_cup_proof_card_enqueue_failed",
            tournament_id=tournament_id,
            error_type=type(exc).__name__,
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
