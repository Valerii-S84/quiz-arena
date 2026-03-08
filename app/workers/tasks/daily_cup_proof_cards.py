from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from aiogram.types import BufferedInputFile

from app.bot.application import build_bot
from app.bot.keyboards.daily_cup import build_daily_cup_share_keyboard, build_daily_cup_share_url
from app.bot.texts.de import TEXTS_DE
from app.core.telegram_links import public_bot_link
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import DAILY_CUP_TOURNAMENT_TYPES, TOURNAMENT_STATUS_COMPLETED
from app.game.tournaments.daily_cup_standings import calculate_daily_cup_standings
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.daily_cup_config import DAILY_CUP_TIMEZONE
from app.workers.tasks.daily_cup_proof_cards_text import (
    build_caption,
    format_points,
    format_user_label,
)
from app.workers.tasks.tournaments_proof_card_render import render_tournament_proof_card_png

logger = structlog.get_logger("app.workers.tasks.daily_cup_proof_cards")


def _is_celery_task(task_obj: object) -> bool:
    return type(task_obj).__module__.startswith("celery.")


def _empty_result() -> dict[str, int]:
    return {"processed": 0, "participants_total": 0, "sent": 0, "cached_reused": 0, "failed": 0}


def _is_today_tournament(*, registration_deadline: datetime, now_utc: datetime) -> bool:
    tz = ZoneInfo(DAILY_CUP_TIMEZONE)
    return registration_deadline.astimezone(tz).date() == now_utc.astimezone(tz).date()


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
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id(session, parsed_tournament_id)
        if (
            tournament is None
            or tournament.type not in DAILY_CUP_TOURNAMENT_TYPES
            or tournament.status != TOURNAMENT_STATUS_COMPLETED
        ):
            return _empty_result()
        if not _is_today_tournament(
            registration_deadline=tournament.registration_deadline,
            now_utc=now_utc,
        ):
            logger.info(
                "daily_cup_proof_cards_skipped_stale_tournament",
                tournament_id=tournament_id,
                registration_deadline=tournament.registration_deadline.isoformat(),
            )
            return _empty_result()

        standings = await calculate_daily_cup_standings(session, tournament_id=parsed_tournament_id)
        if not standings:
            return _empty_result()
        all_participants = [item.participant for item in standings]

        participants = (
            [item for item in all_participants if int(item.user_id) == user_id]
            if user_id is not None
            else all_participants
        )
        if not participants:
            return {
                "processed": 1,
                "participants_total": 0,
                "sent": 0,
                "cached_reused": 0,
                "failed": 0,
            }

        users = await UsersRepo.list_by_ids(
            session, [int(item.user_id) for item in all_participants]
        )
        user_labels = {
            int(user.id): format_user_label(username=user.username, first_name=user.first_name)
            for user in users
        }
        telegram_targets = {int(user.id): int(user.telegram_user_id) for user in users}

    if initial_delay_seconds > 0:
        await asyncio.sleep(max(0, int(initial_delay_seconds)))

    standings_user_ids = [item.user_id for item in standings]
    participant_rows = {int(item.user_id): item for item in participants}
    points_by_user = {int(item.user_id): format_points(item.score) for item in all_participants}
    participants_total = len(standings_user_ids)
    sent = 0
    cached_reused = 0
    failed = 0
    new_file_ids: dict[int, str] = {}

    bot = build_bot()
    try:
        for row in participants:
            current_user_id = int(row.user_id)
            chat_id = telegram_targets.get(current_user_id)
            if chat_id is None:
                failed += 1
                continue
            place = standings_user_ids.index(current_user_id) + 1
            points = points_by_user.get(current_user_id, "0")
            caption = build_caption(place=place, points=points)
            share_url = build_daily_cup_share_url(
                base_link=public_bot_link(),
                share_text=TEXTS_DE["msg.daily_cup.share_template"].format(
                    place=place,
                    total=participants_total,
                    points=points,
                ),
            )
            keyboard = build_daily_cup_share_keyboard(
                tournament_id=tournament_id,
                share_url=share_url,
            )
            cached_file_id = participant_rows[current_user_id].proof_card_file_id
            try:
                if cached_file_id:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=cached_file_id,
                        caption=caption,
                        reply_markup=keyboard,
                    )
                    sent += 1
                    cached_reused += 1
                    continue

                card_png = render_tournament_proof_card_png(
                    player_label=user_labels.get(current_user_id, "Spieler"),
                    place=place,
                    points=points,
                    format_label="7 Fragen",
                    completed_at=now_utc,
                    tournament_name="Daily Arena Cup",
                    rounds_played=4,
                    is_daily_arena=True,
                )
                message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=BufferedInputFile(
                        card_png,
                        filename=f"daily_cup_{tournament_id}_{current_user_id}.png",
                    ),
                    caption=caption,
                    reply_markup=keyboard,
                )
                sent += 1
                if message.photo:
                    new_file_ids[current_user_id] = message.photo[-1].file_id
            except Exception as exc:
                logger.warning(
                    "daily_cup_proof_card_send_failed",
                    tournament_id=tournament_id,
                    user_id=current_user_id,
                    error_type=type(exc).__name__,
                )
                failed += 1
    finally:
        await bot.session.close()

    if new_file_ids:
        async with SessionLocal.begin() as session:
            for current_user_id, file_id in new_file_ids.items():
                await TournamentParticipantsRepo.set_proof_card_file_id_if_missing(
                    session,
                    tournament_id=parsed_tournament_id,
                    user_id=current_user_id,
                    file_id=file_id,
                )

    return {
        "processed": 1,
        "participants_total": participants_total,
        "sent": sent,
        "cached_reused": cached_reused,
        "failed": failed,
    }


def enqueue_daily_cup_proof_cards(
    *,
    tournament_id: str,
    user_id: int | None = None,
    delay_seconds: int = 2,
) -> None:
    try:
        if _is_celery_task(run_daily_cup_proof_cards):
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
