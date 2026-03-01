from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from aiogram.exceptions import TelegramForbiddenError

from app.bot.application import build_bot
from app.bot.texts.de import TEXTS_DE
from app.core.analytics_events import EVENT_SOURCE_WORKER, emit_analytics_event
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import (
    TOURNAMENT_FORMAT_QUICK_5,
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_TYPE_DAILY_ARENA,
)
from app.game.tournaments.internal import generate_invite_code
from app.workers.tasks.daily_cup_config import DAILY_CUP_ROUND_DURATION_MINUTES
from app.workers.tasks.daily_cup_time import get_daily_cup_window


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def round_deadline(*, now_utc_value: datetime) -> datetime:
    return now_utc_value + timedelta(minutes=max(1, int(DAILY_CUP_ROUND_DURATION_MINUTES)))


async def ensure_daily_cup_registration_tournament(
    *,
    session,
    now_utc_value: datetime,
) -> Tournament:
    window = get_daily_cup_window(now_utc=now_utc_value)
    tournament = await TournamentsRepo.get_by_type_and_registration_deadline_for_update(
        session,
        tournament_type=TOURNAMENT_TYPE_DAILY_ARENA,
        registration_deadline=window.close_at_utc,
    )
    if tournament is not None:
        return tournament
    invite_code = await generate_invite_code(session)
    tournament = await TournamentsRepo.create(
        session,
        tournament=Tournament(
            id=uuid4(),
            type=TOURNAMENT_TYPE_DAILY_ARENA,
            created_by=None,
            name="Daily Arena Cup",
            status=TOURNAMENT_STATUS_REGISTRATION,
            format=TOURNAMENT_FORMAT_QUICK_5,
            max_participants=8,
            current_round=0,
            registration_deadline=window.close_at_utc,
            round_deadline=None,
            invite_code=invite_code,
            created_at=now_utc_value,
        ),
    )
    return tournament


async def emit_daily_cup_events(
    *, now_utc_value: datetime, events: list[dict[str, object]]
) -> None:
    if not events:
        return
    async with SessionLocal.begin() as session:
        for event in events:
            payload_raw = event.get("payload")
            await emit_analytics_event(
                session,
                event_type=str(event["event_type"]),
                source=EVENT_SOURCE_WORKER,
                happened_at=now_utc_value,
                user_id=None,
                payload=(payload_raw if isinstance(payload_raw, dict) else {}),
            )


async def send_daily_cup_canceled_messages(
    *,
    telegram_targets: list[int],
    bot_factory: Callable[[], Any] | None = None,
) -> None:
    if not telegram_targets:
        return
    resolved_bot_factory = bot_factory if bot_factory is not None else build_bot
    bot = resolved_bot_factory()
    try:
        for chat_id in telegram_targets:
            try:
                await bot.send_message(chat_id=chat_id, text=TEXTS_DE["msg.daily_cup.canceled"])
            except TelegramForbiddenError:
                continue
            except Exception:
                continue
    finally:
        await bot.session.close()


async def persist_daily_cup_standings_message_ids(
    *,
    tournament_id: UUID,
    new_message_ids: dict[int, int],
    replaced_message_ids: dict[int, int],
) -> None:
    if not new_message_ids and not replaced_message_ids:
        return
    async with SessionLocal.begin() as session:
        for user_id, message_id in new_message_ids.items():
            await TournamentParticipantsRepo.set_standings_message_id_if_missing(
                session,
                tournament_id=tournament_id,
                user_id=user_id,
                message_id=message_id,
            )
        for user_id, message_id in replaced_message_ids.items():
            await TournamentParticipantsRepo.set_standings_message_id(
                session,
                tournament_id=tournament_id,
                user_id=user_id,
                message_id=message_id,
            )
