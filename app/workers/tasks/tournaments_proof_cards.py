from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import structlog

from app.bot.application import build_bot
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.tasks.tournaments_proof_card_render import render_tournament_proof_card_png
from app.workers.tasks.tournaments_proof_cards_delivery import (
    deliver_proof_cards,
    load_proof_card_context,
)

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


def _build_proof_card_result(
    *,
    processed: int,
    participants_total: int,
    sent: int = 0,
    cached_reused: int = 0,
    failed: int = 0,
) -> dict[str, int]:
    return {
        "processed": processed,
        "participants_total": participants_total,
        "sent": sent,
        "cached_reused": cached_reused,
        "failed": failed,
    }


async def run_private_tournament_proof_cards_async(
    *,
    tournament_id: str,
    user_id: int | None = None,
) -> dict[str, int]:
    try:
        parsed_tournament_id = UUID(tournament_id)
    except ValueError:
        return _build_proof_card_result(processed=0, participants_total=0)

    async with SessionLocal.begin() as session:
        context = await load_proof_card_context(
            session=session,
            parsed_tournament_id=parsed_tournament_id,
            user_id=user_id,
            tournaments_repo=TournamentsRepo,
            participants_repo=TournamentParticipantsRepo,
            users_repo=UsersRepo,
            format_points_fn=_format_points,
            format_tournament_format_fn=_format_tournament_format,
            format_user_label_fn=_format_user_label,
        )
        if context is None:
            return _build_proof_card_result(processed=0, participants_total=0)
        if not context.participants:
            return _build_proof_card_result(processed=1, participants_total=0)
    now_utc = datetime.now(timezone.utc)
    delivery_result = await deliver_proof_cards(
        context=context,
        tournament_id=tournament_id,
        now_utc=now_utc,
        session_factory=SessionLocal,
        participants_repo=TournamentParticipantsRepo,
        build_bot_fn=build_bot,
        build_caption_fn=_build_caption,
        render_card_fn=render_tournament_proof_card_png,
        explicit_resend=user_id is not None,
        logger=logger,
    )

    return _build_proof_card_result(
        processed=1,
        participants_total=context.participants_total,
        sent=delivery_result.sent,
        cached_reused=delivery_result.cached_reused,
        failed=delivery_result.failed,
    )


def enqueue_private_tournament_proof_cards(
    *,
    tournament_id: str,
    user_id: int | None = None,
) -> None:
    try:
        if _is_celery_task(run_private_tournament_proof_cards):
            run_private_tournament_proof_cards.delay(
                tournament_id=tournament_id,
                user_id=user_id,
            )
        else:
            run_async_job(
                run_private_tournament_proof_cards_async(
                    tournament_id=tournament_id,
                    user_id=user_id,
                )
            )
    except Exception as exc:
        logger.warning(
            "private_tournament_proof_card_enqueue_failed",
            tournament_id=tournament_id,
            error_type=type(exc).__name__,
        )


@celery_app.task(
    name="app.workers.tasks.tournaments_proof_cards.run_private_tournament_proof_cards"
)
def run_private_tournament_proof_cards(
    *,
    tournament_id: str,
    user_id: int | None = None,
) -> dict[str, int]:
    return run_async_job(
        run_private_tournament_proof_cards_async(
            tournament_id=tournament_id,
            user_id=user_id,
        )
    )
