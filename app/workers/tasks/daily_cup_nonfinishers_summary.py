from __future__ import annotations

from uuid import UUID

import structlog
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import select

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


def _user_did_not_finish_challenge(*, challenge: FriendChallenge, user_id: int) -> bool:
    total_rounds = max(1, int(challenge.total_rounds))
    if int(challenge.creator_user_id) == user_id:
        return (
            challenge.creator_finished_at is None
            and int(challenge.creator_answered_round) < total_rounds
        )
    if challenge.opponent_user_id is not None and int(challenge.opponent_user_id) == user_id:
        return (
            challenge.opponent_finished_at is None
            and int(challenge.opponent_answered_round) < total_rounds
        )
    return False


def _collect_nonfinishers(
    *,
    matches: list,
    challenges_by_id: dict[UUID, FriendChallenge],
) -> set[int]:
    nonfinishers: set[int] = set()
    for match in matches:
        if match.friend_challenge_id is None:
            continue
        challenge = challenges_by_id.get(match.friend_challenge_id)
        if challenge is None:
            continue
        user_a = int(match.user_a)
        if _user_did_not_finish_challenge(challenge=challenge, user_id=user_a):
            nonfinishers.add(user_a)
        if match.user_b is not None:
            user_b = int(match.user_b)
            if _user_did_not_finish_challenge(challenge=challenge, user_id=user_b):
                nonfinishers.add(user_b)
    return nonfinishers


async def run_daily_cup_nonfinishers_summary_async(*, tournament_id: str) -> dict[str, int]:
    try:
        parsed_tournament_id = UUID(tournament_id)
    except ValueError:
        return _empty_result()

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id(session, parsed_tournament_id)
        if (
            tournament is None
            or tournament.type not in DAILY_CUP_TOURNAMENT_TYPES
            or tournament.status != TOURNAMENT_STATUS_COMPLETED
        ):
            return _empty_result()

        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=parsed_tournament_id,
        )
        participant_user_ids = {int(item.user_id) for item in participants}
        participants_total = len(participant_user_ids)
        if not participant_user_ids:
            return _empty_result()

        users = await UsersRepo.list_by_ids(session, sorted(participant_user_ids))
        telegram_targets = {int(user.id): int(user.telegram_user_id) for user in users}

        matches = []
        for round_no in (1, 2, 3):
            round_matches = await TournamentMatchesRepo.list_by_tournament_round(
                session,
                tournament_id=parsed_tournament_id,
                round_no=round_no,
            )
            matches.extend(round_matches)

        challenge_ids = {
            match.friend_challenge_id for match in matches if match.friend_challenge_id is not None
        }
        challenges: list[FriendChallenge] = []
        if challenge_ids:
            result = await session.execute(
                select(FriendChallenge).where(FriendChallenge.id.in_(tuple(challenge_ids)))
            )
            challenges = list(result.scalars().all())
        challenges_by_id = {challenge.id: challenge for challenge in challenges}
        nonfinishers = sorted(
            participant_user_ids
            & _collect_nonfinishers(matches=matches, challenges_by_id=challenges_by_id)
        )

    if not nonfinishers:
        return {
            "processed": 1,
            "participants_total": participants_total,
            "nonfinishers_total": 0,
            "sent": 0,
            "failed": 0,
        }

    sent = 0
    failed = 0
    text = TEXTS_DE["msg.daily_cup.not_finished_summary"]
    bot = build_bot()
    try:
        for user_id in nonfinishers:
            chat_id = telegram_targets.get(user_id)
            if chat_id is None:
                failed += 1
                continue
            try:
                await bot.send_message(chat_id=chat_id, text=text)
                sent += 1
            except TelegramForbiddenError:
                failed += 1
            except Exception:
                failed += 1
    finally:
        await bot.session.close()

    return {
        "processed": 1,
        "participants_total": participants_total,
        "nonfinishers_total": len(nonfinishers),
        "sent": sent,
        "failed": failed,
    }


def enqueue_daily_cup_nonfinishers_summary(*, tournament_id: str, delay_seconds: int = 0) -> None:
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
    return run_async_job(run_daily_cup_nonfinishers_summary_async(tournament_id=tournament_id))


__all__ = [
    "enqueue_daily_cup_nonfinishers_summary",
    "run_daily_cup_nonfinishers_summary",
    "run_daily_cup_nonfinishers_summary_async",
]
