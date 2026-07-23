from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog

from app.bot.application import build_bot
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import DAILY_CUP_TOURNAMENT_TYPES
from app.game.tournaments.daily_cup_standings import calculate_daily_cup_standings
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.task_heartbeat import run_tracked_async_job
from app.workers.tasks.daily_cup_config import DAILY_CUP_TIMEZONE
from app.workers.tasks.daily_cup_core import persist_daily_cup_standings_message_ids
from app.workers.tasks.daily_cup_messaging_context import load_daily_cup_round_messaging_context
from app.workers.tasks.daily_cup_messaging_delivery import deliver_daily_cup_messages
from app.workers.tasks.daily_cup_messaging_followups import handle_daily_cup_completion_followups
from app.workers.tasks.daily_cup_task_helpers import is_celery_task, is_today_daily_cup_tournament
from app.workers.tasks.tournaments_messaging_text import (
    ROUND_STATUSES,
    format_points,
    format_user_label,
)

logger = structlog.get_logger("app.workers.tasks.daily_cup_messaging")


def _empty_result() -> dict[str, int]:
    return {"processed": 0, "participants_total": 0, "sent": 0, "edited": 0, "failed": 0}


async def run_daily_cup_round_messaging_async(*, tournament_id: str) -> dict[str, int]:
    return await run_daily_cup_round_messaging_async_with_followups(
        tournament_id=tournament_id, enqueue_completion_followups=False
    )


async def run_daily_cup_round_messaging_async_with_followups(
    *,
    tournament_id: str,
    enqueue_completion_followups: bool,
) -> dict[str, int]:
    try:
        parsed_tournament_id = UUID(tournament_id)
    except ValueError:
        return _empty_result()

    now_utc_value = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        context = await load_daily_cup_round_messaging_context(
            session=session,
            parsed_tournament_id=parsed_tournament_id,
            now_utc_value=now_utc_value,
            tournaments_repo=TournamentsRepo,
            matches_repo=TournamentMatchesRepo,
            users_repo=UsersRepo,
            calculate_standings_fn=calculate_daily_cup_standings,
            format_points_fn=format_points,
            format_user_label_fn=format_user_label,
            is_today_daily_cup_tournament_fn=is_today_daily_cup_tournament,
            daily_cup_tournament_types=DAILY_CUP_TOURNAMENT_TYPES,
            round_statuses=ROUND_STATUSES,
            timezone_name=DAILY_CUP_TIMEZONE,
        )
    if context is None:
        return _empty_result()

    bot = build_bot()
    try:
        delivery = await deliver_daily_cup_messages(
            bot=bot,
            tournament=context.tournament,
            round_matches=context.round_matches,
            standings_user_ids=context.standings_user_ids,
            labels=context.labels,
            telegram_targets=context.telegram_targets,
            points_by_user=context.points_by_user,
            tie_breaks_by_user=context.tie_breaks_by_user,
            place_by_user=context.place_by_user,
            participant_rows=context.participant_rows,
            participants_total=context.participants_total,
        )
    finally:
        await bot.session.close()

    await persist_daily_cup_standings_message_ids(
        tournament_id=context.parsed_tournament_id,
        new_message_ids=dict(delivery["new_message_ids"]),
        replaced_message_ids=dict(delivery["replaced_message_ids"]),
    )
    handle_daily_cup_completion_followups(
        is_completed=context.is_completed,
        enqueue_completion_followups=enqueue_completion_followups,
        allow_completion_followups=context.allow_completion_followups,
        tournament_id=tournament_id,
        registration_deadline=context.registration_deadline,
        logger=logger,
    )

    return {
        "processed": 1,
        "participants_total": context.participants_total,
        "sent": int(delivery["sent"]),
        "edited": int(delivery["edited"]),
        "failed": int(delivery["failed"]),
    }


def enqueue_daily_cup_round_messaging(
    *,
    tournament_id: str,
    enqueue_completion_followups: bool = False,
) -> None:
    try:
        if is_celery_task(run_daily_cup_round_messaging):
            run_daily_cup_round_messaging.delay(
                tournament_id=tournament_id,
                enqueue_completion_followups=enqueue_completion_followups,
            )
        else:
            run_async_job(
                run_daily_cup_round_messaging_async_with_followups(
                    tournament_id=tournament_id,
                    enqueue_completion_followups=enqueue_completion_followups,
                )
            )
    except Exception as exc:
        logger.warning(
            "daily_cup_round_message_enqueue_failed",
            tournament_id=tournament_id,
            error_type=type(exc).__name__,
        )


@celery_app.task(name="app.workers.tasks.daily_cup.run_daily_cup_round_messaging")
def run_daily_cup_round_messaging(
    *,
    tournament_id: str,
    enqueue_completion_followups: bool = False,
) -> dict[str, int]:
    task_name = "app.workers.tasks.daily_cup.run_daily_cup_round_messaging"
    return run_tracked_async_job(
        task_name=task_name,
        schedule_key="daily-cup-round-messaging-on-demand",
        awaitable=run_daily_cup_round_messaging_async_with_followups(
            tournament_id=tournament_id,
            enqueue_completion_followups=enqueue_completion_followups,
        ),
    )
