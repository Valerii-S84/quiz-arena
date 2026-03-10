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
from app.workers.tasks.daily_cup_config import DAILY_CUP_TIMEZONE
from app.workers.tasks.daily_cup_core import persist_daily_cup_standings_message_ids
from app.workers.tasks.daily_cup_messaging_delivery import deliver_daily_cup_messages
from app.workers.tasks.daily_cup_messaging_followups import handle_daily_cup_completion_followups
from app.workers.tasks.daily_cup_task_helpers import is_celery_task, is_today_daily_cup_tournament
from app.workers.tasks.tournaments_messaging_text import (
    ROUND_STATUSES,
    format_points,
    format_user_label,
)

logger = structlog.get_logger("app.workers.tasks.daily_cup_messaging")


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
        return {"processed": 0, "participants_total": 0, "sent": 0, "edited": 0, "failed": 0}

    is_completed = False
    allow_completion_followups = False
    registration_deadline: datetime | None = None
    now_utc_value = datetime.now(timezone.utc)
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id(session, parsed_tournament_id)
        if (
            tournament is None
            or tournament.type not in DAILY_CUP_TOURNAMENT_TYPES
            or tournament.status in {"REGISTRATION", "CANCELED"}
        ):
            return {"processed": 0, "participants_total": 0, "sent": 0, "edited": 0, "failed": 0}
        standings = await calculate_daily_cup_standings(session, tournament_id=parsed_tournament_id)
        if not standings:
            return {"processed": 0, "participants_total": 0, "sent": 0, "edited": 0, "failed": 0}
        participants = [item.participant for item in standings]

        users = await UsersRepo.list_by_ids(session, [int(item.user_id) for item in participants])
        labels = {
            int(user.id): format_user_label(username=user.username, first_name=user.first_name)
            for user in users
        }
        telegram_targets = {int(user.id): int(user.telegram_user_id) for user in users}

        round_matches = []
        if tournament.status in ROUND_STATUSES:
            round_matches = await TournamentMatchesRepo.list_by_tournament_round(
                session,
                tournament_id=parsed_tournament_id,
                round_no=int(tournament.current_round),
            )
        is_completed = tournament.status == "COMPLETED"
        registration_deadline = tournament.registration_deadline
        if is_completed:
            allow_completion_followups = is_today_daily_cup_tournament(
                registration_deadline=tournament.registration_deadline,
                now_utc=now_utc_value,
                timezone_name=DAILY_CUP_TIMEZONE,
            )

    standings_user_ids = [item.user_id for item in standings]
    points_by_user = {int(item.user_id): format_points(item.score) for item in participants}
    tie_breaks_by_user = {int(item.user_id): format_points(item.tie_break) for item in participants}
    place_by_user = {item.user_id: item.place for item in standings}
    participant_rows = {int(item.user_id): item for item in participants}
    participants_total = len(standings_user_ids)

    sent = edited = failed = 0
    new_message_ids: dict[int, int] = {}
    replaced_message_ids: dict[int, int] = {}

    bot = build_bot()
    try:
        delivery = await deliver_daily_cup_messages(
            bot=bot,
            tournament=tournament,
            round_matches=round_matches,
            standings_user_ids=standings_user_ids,
            labels=labels,
            telegram_targets=telegram_targets,
            points_by_user=points_by_user,
            tie_breaks_by_user=tie_breaks_by_user,
            place_by_user=place_by_user,
            participant_rows=participant_rows,
            participants_total=participants_total,
        )
        sent = int(delivery["sent"])
        edited = int(delivery["edited"])
        failed = int(delivery["failed"])
        new_message_ids = dict(delivery["new_message_ids"])
        replaced_message_ids = dict(delivery["replaced_message_ids"])
    finally:
        await bot.session.close()

    await persist_daily_cup_standings_message_ids(
        tournament_id=parsed_tournament_id,
        new_message_ids=new_message_ids,
        replaced_message_ids=replaced_message_ids,
    )
    handle_daily_cup_completion_followups(
        is_completed=is_completed,
        enqueue_completion_followups=enqueue_completion_followups,
        allow_completion_followups=allow_completion_followups,
        tournament_id=tournament_id,
        registration_deadline=registration_deadline,
        logger=logger,
    )

    return {
        "processed": 1,
        "participants_total": participants_total,
        "sent": sent,
        "edited": edited,
        "failed": failed,
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
    return run_async_job(
        run_daily_cup_round_messaging_async_with_followups(
            tournament_id=tournament_id, enqueue_completion_followups=enqueue_completion_followups
        )
    )
