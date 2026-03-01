from __future__ import annotations

import urllib.parse
from uuid import UUID

import structlog
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.application import build_bot
from app.bot.keyboards.tournament import build_tournament_lobby_keyboard
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import TOURNAMENT_STATUS_COMPLETED
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app
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
    bot_username: str,
    invite_code: str,
    tournament_name: str | None,
) -> str:
    share_text = urllib.parse.quote(
        f"🏆 Ich spiele im {tournament_name or 'Deutsch-Turnier'}! "
        f"Komm dazu → t.me/{bot_username}?start=tournament_{invite_code}"
    )
    return f"https://t.me/share/url?url={share_text}"


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
        return {"processed": 0, "participants_total": 0, "sent": 0, "edited": 0, "failed": 0}

    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_id(session, parsed_tournament_id)
        if tournament is None or tournament.status in {"REGISTRATION", "CANCELED"}:
            return {"processed": 0, "participants_total": 0, "sent": 0, "edited": 0, "failed": 0}
        participants = await TournamentParticipantsRepo.list_for_tournament(
            session,
            tournament_id=parsed_tournament_id,
        )
        if not participants:
            return {"processed": 0, "participants_total": 0, "sent": 0, "edited": 0, "failed": 0}

        users = await UsersRepo.list_by_ids(session, [int(item.user_id) for item in participants])
        labels: dict[int, str] = {}
        telegram_targets: dict[int, int] = {}
        for user in users:
            user_id = int(user.id)
            labels[user_id] = format_user_label(
                username=user.username,
                first_name=user.first_name,
            )
            telegram_targets[user_id] = int(user.telegram_user_id)

        round_matches = []
        if tournament.status in ROUND_STATUSES:
            round_matches = await TournamentMatchesRepo.list_by_tournament_round(
                session,
                tournament_id=parsed_tournament_id,
                round_no=int(tournament.current_round),
            )

    standings_user_ids = [int(item.user_id) for item in participants]
    points_by_user = {int(item.user_id): format_points(item.score) for item in participants}
    place_by_user = {user_id: place for place, user_id in enumerate(standings_user_ids, start=1)}
    participant_rows = {int(item.user_id): item for item in participants}
    participants_total = len(standings_user_ids)

    sent = 0
    edited = 0
    failed = 0
    new_message_ids: dict[int, int] = {}
    replaced_message_ids: dict[int, int] = {}

    bot = build_bot()
    bot_username: str | None = None
    try:
        try:
            me = await bot.get_me()
            if me.username:
                bot_username = me.username
        except Exception:
            bot_username = None
        for user_id in standings_user_ids:
            chat_id = telegram_targets.get(user_id)
            if chat_id is None:
                failed += 1
                continue

            play_challenge_id, opponent_user_id = resolve_match_context(
                round_matches=round_matches,
                viewer_user_id=user_id,
            )
            standings_lines = build_standings_lines(
                standings_user_ids=standings_user_ids,
                labels=labels,
                points_by_user=points_by_user,
                viewer_user_id=user_id,
            )
            if tournament.status == TOURNAMENT_STATUS_COMPLETED:
                text = build_completed_text(
                    tournament_name=tournament.name,
                    tournament_format=tournament.format,
                    place=place_by_user[user_id],
                    my_points=points_by_user.get(user_id, "0"),
                    standings_lines=standings_lines,
                )
            else:
                text = build_round_text(
                    tournament_name=tournament.name,
                    tournament_format=tournament.format,
                    round_no=max(1, int(tournament.current_round)),
                    deadline_text=format_deadline(tournament.round_deadline),
                    opponent_label=(
                        labels.get(opponent_user_id) if opponent_user_id is not None else None
                    ),
                    standings_lines=standings_lines,
                )
            keyboard = build_tournament_lobby_keyboard(
                invite_code=tournament.invite_code,
                tournament_id=str(tournament.id),
                can_join=False,
                can_start=False,
                play_challenge_id=play_challenge_id,
                show_share_result=tournament.status == TOURNAMENT_STATUS_COMPLETED,
            )
            if bot_username is not None:
                keyboard = _with_standings_share_button(
                    keyboard=keyboard,
                    share_url=_build_standings_share_url(
                        bot_username=bot_username,
                        invite_code=tournament.invite_code,
                        tournament_name=tournament.name,
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
    except Exception as exc:
        logger.warning(
            "private_tournament_round_message_failed",
            tournament_id=tournament_id,
            error_type=type(exc).__name__,
        )
        failed += 1
    finally:
        await bot.session.close()

    if new_message_ids or replaced_message_ids:
        async with SessionLocal.begin() as session:
            for user_id, message_id in new_message_ids.items():
                await TournamentParticipantsRepo.set_standings_message_id_if_missing(
                    session,
                    tournament_id=parsed_tournament_id,
                    user_id=user_id,
                    message_id=message_id,
                )
            for user_id, message_id in replaced_message_ids.items():
                await TournamentParticipantsRepo.set_standings_message_id(
                    session,
                    tournament_id=parsed_tournament_id,
                    user_id=user_id,
                    message_id=message_id,
                )

    return {
        "processed": 1,
        "participants_total": participants_total,
        "sent": sent,
        "edited": edited,
        "failed": failed,
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
    return run_async_job(run_private_tournament_round_messaging_async(tournament_id=tournament_id))
