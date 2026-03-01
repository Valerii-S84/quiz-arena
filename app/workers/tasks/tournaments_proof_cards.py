from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import structlog
from aiogram.types import BufferedInputFile

from app.bot.application import build_bot
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import TOURNAMENT_STATUS_COMPLETED
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.tournaments_proof_card_render import render_tournament_proof_card_png

logger = structlog.get_logger("app.workers.tasks.tournaments_proof_cards")


def _is_celery_task(task_obj: object) -> bool:
    return type(task_obj).__module__.startswith("celery.")


def _format_user_label(*, username: str | None, first_name: str | None) -> str:
    if username:
        cleaned = username.strip()
        if cleaned:
            return f"@{cleaned}"
    if first_name:
        cleaned = first_name.strip()
        if cleaned:
            return cleaned
    return "Spieler"


def _format_points(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(int(normalized))
    return format(normalized, "f").rstrip("0").rstrip(".")


def _format_tournament_format(format_code: str) -> str:
    return "12 Fragen" if format_code == "QUICK_12" else "5 Fragen"


def _build_caption(*, place: int, points: str) -> str:
    return f"🏆 Turnier abgeschlossen\nPlatz #{place}\nPunkte: {points}"


async def run_private_tournament_proof_cards_async(*, tournament_id: str) -> dict[str, int]:
    try:
        parsed_tournament_id = UUID(tournament_id)
    except ValueError:
        return {
            "processed": 0,
            "participants_total": 0,
            "sent": 0,
            "cached_reused": 0,
            "failed": 0,
        }

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id(session, parsed_tournament_id)
        if tournament is None or tournament.status != TOURNAMENT_STATUS_COMPLETED:
            return {
                "processed": 0,
                "participants_total": 0,
                "sent": 0,
                "cached_reused": 0,
                "failed": 0,
            }
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=parsed_tournament_id,
        )
        if not participants:
            return {
                "processed": 0,
                "participants_total": 0,
                "sent": 0,
                "cached_reused": 0,
                "failed": 0,
            }
        users = await UsersRepo.list_by_ids(session, [int(item.user_id) for item in participants])
        user_labels = {
            int(user.id): _format_user_label(username=user.username, first_name=user.first_name)
            for user in users
        }
        telegram_targets = {int(user.id): int(user.telegram_user_id) for user in users}
        tournament_format = _format_tournament_format(tournament.format)

    participant_rows = {int(item.user_id): item for item in participants}
    standings_user_ids = [int(item.user_id) for item in participants]
    points_by_user = {int(item.user_id): _format_points(item.score) for item in participants}
    participants_total = len(standings_user_ids)
    now_utc = datetime.now(timezone.utc)

    sent = 0
    cached_reused = 0
    failed = 0
    new_file_ids: dict[int, str] = {}

    bot = build_bot()
    try:
        for place, user_id in enumerate(standings_user_ids, start=1):
            chat_id = telegram_targets.get(user_id)
            if chat_id is None:
                failed += 1
                continue
            points = points_by_user.get(user_id, "0")
            caption = _build_caption(place=place, points=points)
            cached_file_id = participant_rows[user_id].proof_card_file_id
            try:
                if cached_file_id:
                    await bot.send_photo(chat_id=chat_id, photo=cached_file_id, caption=caption)
                    sent += 1
                    cached_reused += 1
                    continue

                card_png = render_tournament_proof_card_png(
                    player_label=user_labels.get(user_id, "Spieler"),
                    place=place,
                    points=points,
                    format_label=tournament_format,
                    completed_at=now_utc,
                    tournament_name=tournament.name,
                    rounds_played=tournament.current_round,
                )
                message = await bot.send_photo(
                    chat_id=chat_id,
                    photo=BufferedInputFile(
                        card_png,
                        filename=f"tournament_{tournament_id}_{user_id}.png",
                    ),
                    caption=caption,
                )
                sent += 1
                if message.photo:
                    new_file_ids[user_id] = message.photo[-1].file_id
            except Exception as exc:
                logger.warning(
                    "private_tournament_proof_card_send_failed",
                    tournament_id=tournament_id,
                    user_id=user_id,
                    error_type=type(exc).__name__,
                )
                failed += 1
    finally:
        await bot.session.close()

    if new_file_ids:
        async with SessionLocal.begin() as session:
            for user_id, file_id in new_file_ids.items():
                await TournamentParticipantsRepo.set_proof_card_file_id_if_missing(
                    session,
                    tournament_id=parsed_tournament_id,
                    user_id=user_id,
                    file_id=file_id,
                )

    return {
        "processed": 1,
        "participants_total": participants_total,
        "sent": sent,
        "cached_reused": cached_reused,
        "failed": failed,
    }


def enqueue_private_tournament_proof_cards(*, tournament_id: str) -> None:
    try:
        if _is_celery_task(run_private_tournament_proof_cards):
            run_private_tournament_proof_cards.delay(tournament_id=tournament_id)
        else:
            run_async_job(run_private_tournament_proof_cards_async(tournament_id=tournament_id))
    except Exception as exc:
        logger.warning(
            "private_tournament_proof_card_enqueue_failed",
            tournament_id=tournament_id,
            error_type=type(exc).__name__,
        )


@celery_app.task(
    name="app.workers.tasks.tournaments_proof_cards.run_private_tournament_proof_cards"
)
def run_private_tournament_proof_cards(*, tournament_id: str) -> dict[str, int]:
    return run_async_job(run_private_tournament_proof_cards_async(tournament_id=tournament_id))
