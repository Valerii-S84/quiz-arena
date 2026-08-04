from __future__ import annotations

from uuid import UUID

import structlog

from app.bot.application import build_bot
from app.bot.texts.de import TEXTS_DE
from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import DAILY_CUP_TOURNAMENT_TYPES, TOURNAMENT_STATUS_COMPLETED
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.daily_cup_nonfinishers_summary_context import (
    collect_nonfinishers,
    load_daily_cup_nonfinishers_summary_context,
    user_did_not_finish_challenge,
)
from app.workers.tasks.daily_cup_nonfinishers_summary_delivery import (
    deliver_daily_cup_nonfinishers_summary,
)
from app.workers.tasks.daily_cup_task_helpers import (
    disabled_daily_cup_task_result,
    is_daily_cup_enabled,
)

logger = structlog.get_logger("app.workers.tasks.daily_cup_nonfinishers_summary")


def _is_celery_task(task_obj: object) -> bool:
    return type(task_obj).__module__.startswith("celery.")


def _empty_result() -> dict[str, int]:
    return {
        "processed": 0,
        "participants_total": 0,
        "nonfinishers_total": 0,
        "sent": 0,
        "failed": 0,
    }


def _user_did_not_finish_challenge(*, challenge, user_id: int) -> bool:
    return user_did_not_finish_challenge(challenge=challenge, user_id=user_id)


def _collect_nonfinishers(
    *,
    matches: list,
    challenges_by_id: dict[UUID, FriendChallenge],
) -> set[int]:
    return collect_nonfinishers(matches=matches, challenges_by_id=challenges_by_id)


async def run_daily_cup_nonfinishers_summary_async(*, tournament_id: str) -> dict[str, int]:
    try:
        parsed_tournament_id = UUID(tournament_id)
    except ValueError:
        return _empty_result()

    async with SessionLocal.begin() as session:
        context = await load_daily_cup_nonfinishers_summary_context(
            session=session,
            parsed_tournament_id=parsed_tournament_id,
            tournaments_repo=TournamentsRepo,
            participants_repo=TournamentParticipantsRepo,
            users_repo=UsersRepo,
            matches_repo=TournamentMatchesRepo,
            daily_cup_tournament_types=DAILY_CUP_TOURNAMENT_TYPES,
            tournament_completed_status=TOURNAMENT_STATUS_COMPLETED,
            collect_nonfinishers_fn=_collect_nonfinishers,
        )
    if context is None:
        return _empty_result()

    if not context.nonfinishers:
        return {
            "processed": 1,
            "participants_total": context.participants_total,
            "nonfinishers_total": 0,
            "sent": 0,
            "failed": 0,
        }

    bot = build_bot()
    try:
        delivery = await deliver_daily_cup_nonfinishers_summary(
            bot=bot,
            nonfinishers=context.nonfinishers,
            telegram_targets=context.telegram_targets,
            text=TEXTS_DE["msg.daily_cup.not_finished_summary"],
        )
    finally:
        await bot.session.close()

    return {
        "processed": 1,
        "participants_total": context.participants_total,
        "nonfinishers_total": len(context.nonfinishers),
        "sent": delivery.sent,
        "failed": delivery.failed,
    }


def enqueue_daily_cup_nonfinishers_summary(*, tournament_id: str, delay_seconds: int = 0) -> None:
    if not is_daily_cup_enabled():
        return
    try:
        if _is_celery_task(run_daily_cup_nonfinishers_summary):
            run_daily_cup_nonfinishers_summary.apply_async(
                kwargs={"tournament_id": tournament_id},
                countdown=max(0, int(delay_seconds)),
            )
            return
        run_async_job(run_daily_cup_nonfinishers_summary_async(tournament_id=tournament_id))
    except Exception as exc:
        logger.warning(
            "daily_cup_nonfinishers_summary_enqueue_failed",
            tournament_id=tournament_id,
            error_type=type(exc).__name__,
        )


@celery_app.task(name="app.workers.tasks.daily_cup.run_daily_cup_nonfinishers_summary")
def run_daily_cup_nonfinishers_summary(*, tournament_id: str) -> dict[str, int]:
    if not is_daily_cup_enabled():
        return disabled_daily_cup_task_result()
    return run_async_job(run_daily_cup_nonfinishers_summary_async(tournament_id=tournament_id))


__all__ = [
    "enqueue_daily_cup_nonfinishers_summary",
    "run_daily_cup_nonfinishers_summary",
    "run_daily_cup_nonfinishers_summary_async",
]
