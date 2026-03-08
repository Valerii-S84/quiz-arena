from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from app.bot.application import build_bot
from app.bot.keyboards.daily_cup import build_daily_cup_lobby_keyboard, build_daily_cup_share_url
from app.bot.texts.de import TEXTS_DE
from app.core.telegram_links import public_bot_link
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
from app.workers.tasks.daily_cup_messaging_text import (
    build_completed_text,
    build_round_text,
    build_standings_lines,
)
from app.workers.tasks.tournaments_messaging_text import (
    ROUND_STATUSES,
    format_deadline,
    format_points,
    format_user_label,
    is_message_not_modified_error,
    resolve_match_context,
)

logger = structlog.get_logger("app.workers.tasks.daily_cup_messaging")


def _is_celery_task(task_obj: object) -> bool:
    return type(task_obj).__module__.startswith("celery.")


def _is_today_tournament(*, registration_deadline: datetime, now_utc: datetime) -> bool:
    tz = ZoneInfo(DAILY_CUP_TIMEZONE)
    return registration_deadline.astimezone(tz).date() == now_utc.astimezone(tz).date()


async def run_daily_cup_round_messaging_async(*, tournament_id: str) -> dict[str, int]:
    return await run_daily_cup_round_messaging_async_with_followups(
        tournament_id=tournament_id,
        enqueue_completion_followups=False,
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
            allow_completion_followups = _is_today_tournament(
                registration_deadline=tournament.registration_deadline,
                now_utc=now_utc_value,
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
        for user_id in standings_user_ids:
            chat_id = telegram_targets.get(user_id)
            if chat_id is None:
                failed += 1
                continue

            play_challenge_id, opponent_user_id = resolve_match_context(
                round_matches=round_matches, viewer_user_id=user_id
            )
            standings_lines = build_standings_lines(
                standings_user_ids=standings_user_ids,
                labels=labels,
                points_by_user=points_by_user,
                viewer_user_id=user_id,
                tie_breaks_by_user=(
                    tie_breaks_by_user if tournament.status == "COMPLETED" else None
                ),
            )
            if tournament.status == "COMPLETED":
                text = build_completed_text(
                    place=place_by_user[user_id],
                    my_points=points_by_user.get(user_id, "0"),
                    standings_lines=standings_lines,
                )
            else:
                text = build_round_text(
                    round_no=max(1, int(tournament.current_round)),
                    deadline_text=format_deadline(tournament.round_deadline),
                    opponent_label=(
                        labels.get(opponent_user_id) if opponent_user_id is not None else None
                    ),
                    standings_lines=standings_lines,
                )
            keyboard = build_daily_cup_lobby_keyboard(
                tournament_id=str(tournament.id),
                can_join=False,
                play_challenge_id=play_challenge_id,
                show_share_result=tournament.status == "COMPLETED",
                show_proof_card=tournament.status == "COMPLETED",
                share_url=(
                    build_daily_cup_share_url(
                        base_link=public_bot_link(),
                        share_text=TEXTS_DE["msg.daily_cup.share_template"].format(
                            place=place_by_user[user_id],
                            total=participants_total,
                            points=points_by_user.get(user_id, "0"),
                        ),
                    )
                    if tournament.status == "COMPLETED"
                    else None
                ),
            )
            existing_message_id = participant_rows[user_id].standings_message_id
            if existing_message_id is None:
                message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
                sent += 1
                new_message_ids[user_id] = int(message.message_id)
                continue

            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=int(existing_message_id),
                    text=text,
                    reply_markup=keyboard,
                )
                edited += 1
            except Exception as exc:
                if is_message_not_modified_error(exc):
                    edited += 1
                    continue
                message = await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
                sent += 1
                replaced_message_ids[user_id] = int(message.message_id)
    finally:
        await bot.session.close()

    await persist_daily_cup_standings_message_ids(
        tournament_id=parsed_tournament_id,
        new_message_ids=new_message_ids,
        replaced_message_ids=replaced_message_ids,
    )
    if is_completed and enqueue_completion_followups:
        if allow_completion_followups:
            from app.workers.tasks.daily_cup_nonfinishers_summary import (
                enqueue_daily_cup_nonfinishers_summary,
            )
            from app.workers.tasks.daily_cup_proof_cards import enqueue_daily_cup_proof_cards

            enqueue_daily_cup_proof_cards(tournament_id=tournament_id, delay_seconds=2)
            enqueue_daily_cup_nonfinishers_summary(tournament_id=tournament_id)
        else:
            logger.info(
                "daily_cup_completion_followups_skipped_stale_tournament",
                tournament_id=tournament_id,
                registration_deadline=(
                    registration_deadline.isoformat() if registration_deadline is not None else None
                ),
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
        if _is_celery_task(run_daily_cup_round_messaging):
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
            tournament_id=tournament_id,
            enqueue_completion_followups=enqueue_completion_followups,
        )
    )
