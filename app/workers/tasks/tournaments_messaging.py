from __future__ import annotations

from uuid import UUID

import structlog
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.application import build_bot
from app.bot.keyboards.tournament import build_tournament_lobby_keyboard, build_tournament_share_url
from app.core.telegram_links import public_bot_start_link
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
from app.workers.task_heartbeat import run_tracked_async_job
from app.workers.tasks.tournaments_messaging_context import load_round_messaging_context
from app.workers.tasks.tournaments_messaging_delivery import deliver_round_messages
from app.workers.tasks.tournaments_messaging_persistence import persist_standings_message_ids
from app.workers.tasks.tournaments_messaging_text import (
    ROUND_STATUSES,
    build_completed_text,
    build_round_text,
    build_standings_lines,
    format_deadline,
    format_points,
    format_user_label,
    is_message_not_modified_error,
    resolve_match_context,
)

logger = structlog.get_logger("app.workers.tasks.tournaments_messaging")


def _is_celery_task(task_obj: object) -> bool:
    return type(task_obj).__module__.startswith("celery.")


def _build_standings_share_url(
    *,
    invite_code: str,
    tournament_name: str | None,
) -> str:
    invite_link = public_bot_start_link(start_param=f"tournament_{invite_code}")
    share_text = f"🏆 Ich spiele im {tournament_name or 'Deutsch-Turnier'}! " "Komm dazu →"
    return build_tournament_share_url(base_link=invite_link, share_text=share_text)


def _with_standings_share_button(
    *,
    keyboard: InlineKeyboardMarkup,
    share_url: str,
) -> InlineKeyboardMarkup:
    rows = [list(row) for row in keyboard.inline_keyboard]
    insert_at = max(0, len(rows) - 1)
    rows.insert(insert_at, [InlineKeyboardButton(text="📤 Tabelle teilen", url=share_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def run_private_tournament_round_messaging_async(*, tournament_id: str) -> dict[str, int]:
    try:
        parsed_tournament_id = UUID(tournament_id)
    except ValueError:
        return {
            "processed": 0,
            "participants_total": 0,
            "sent": 0,
            "edited": 0,
            "failed": 0,
            "skipped": 0,
        }

    async with SessionLocal.begin() as session:
        context = await load_round_messaging_context(
            session=session,
            parsed_tournament_id=parsed_tournament_id,
            tournaments_repo=TournamentsRepo,
            participants_repo=TournamentParticipantsRepo,
            users_repo=UsersRepo,
            matches_repo=TournamentMatchesRepo,
            format_points_fn=format_points,
            round_statuses=ROUND_STATUSES,
            format_user_label_fn=format_user_label,
        )
        if context is None:
            return {
                "processed": 0,
                "participants_total": 0,
                "sent": 0,
                "edited": 0,
                "failed": 0,
                "skipped": 0,
            }
    delivery_result = await deliver_round_messages(
        context=context,
        build_bot_fn=build_bot,
        resolve_match_context_fn=resolve_match_context,
        build_standings_lines_fn=build_standings_lines,
        build_completed_text_fn=build_completed_text,
        build_round_text_fn=build_round_text,
        format_deadline_fn=format_deadline,
        build_keyboard_fn=build_tournament_lobby_keyboard,
        add_share_button_fn=_with_standings_share_button,
        build_share_url_fn=_build_standings_share_url,
        is_message_not_modified_error_fn=is_message_not_modified_error,
        logger=logger,
    )

    if delivery_result.new_message_ids or delivery_result.replaced_message_ids:
        async with SessionLocal.begin() as session:
            await persist_standings_message_ids(
                session=session,
                parsed_tournament_id=parsed_tournament_id,
                participants_repo=TournamentParticipantsRepo,
                new_message_ids=delivery_result.new_message_ids,
                replaced_message_ids=delivery_result.replaced_message_ids,
            )

    return {
        "processed": 1,
        "participants_total": len(context.standings_user_ids),
        "sent": delivery_result.sent,
        "edited": delivery_result.edited,
        "failed": delivery_result.failed,
        "skipped": delivery_result.skipped,
    }


def enqueue_private_tournament_round_messaging(*, tournament_id: str) -> None:
    try:
        if _is_celery_task(run_private_tournament_round_messaging):
            run_private_tournament_round_messaging.delay(tournament_id=tournament_id)
        else:
            run_async_job(run_private_tournament_round_messaging_async(tournament_id=tournament_id))
    except Exception as exc:
        logger.warning(
            "private_tournament_round_message_enqueue_failed",
            tournament_id=tournament_id,
            error_type=type(exc).__name__,
        )


@celery_app.task(
    name="app.workers.tasks.tournaments_messaging.run_private_tournament_round_messaging"
)
def run_private_tournament_round_messaging(*, tournament_id: str) -> dict[str, int]:
    task_name = "app.workers.tasks.tournaments_messaging.run_private_tournament_round_messaging"
    return run_tracked_async_job(
        task_name=task_name,
        schedule_key="private-tournament-round-messaging-on-demand",
        awaitable=run_private_tournament_round_messaging_async(tournament_id=tournament_id),
    )
