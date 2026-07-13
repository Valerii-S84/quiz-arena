from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from app.bot.application import build_bot
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
from app.services.telegram_delivery import TelegramDeliveryTarget, begin_telegram_delivery_dispatch
from app.services.telegram_delivery import (
    build_delivery_idempotency_key as build_delivery_idempotency_key,
)
from app.services.telegram_delivery import hash_chat_id as hash_chat_id
from app.services.telegram_delivery import (
    mark_telegram_delivery_failed,
    mark_telegram_delivery_sent,
    prepare_telegram_delivery,
)
from app.workers.tasks.daily_cup_cancel_delivery import (
    DailyCupCancelDeliveryOperations,
    daily_cup_cancel_delivery_target,
)
from app.workers.tasks.daily_cup_cancel_delivery import (
    send_daily_cup_canceled_messages as _send_daily_cup_canceled_messages,
)
from app.workers.tasks.daily_cup_config import TOURNAMENT_MAX_PARTICIPANTS
from app.workers.tasks.daily_cup_persistence import emit_daily_cup_events as _emit_daily_cup_events
from app.workers.tasks.daily_cup_persistence import (
    persist_daily_cup_standings_message_ids as _persist_daily_cup_standings_message_ids,
)
from app.workers.tasks.daily_cup_time import get_daily_cup_window


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


async def _lock_daily_cup_registration_slot(
    *,
    session,
    tournament_type: str,
    registration_deadline: datetime,
) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{tournament_type}:{registration_deadline.isoformat()}"},
    )


async def ensure_daily_cup_registration_tournament(
    *,
    session,
    now_utc_value: datetime,
) -> Tournament:
    tournament_type = TOURNAMENT_TYPE_DAILY_ARENA
    window = get_daily_cup_window(now_utc=now_utc_value)
    await _lock_daily_cup_registration_slot(
        session=session,
        tournament_type=tournament_type,
        registration_deadline=window.close_at_utc,
    )
    tournament = await TournamentsRepo.get_by_type_and_registration_deadline_for_update(
        session,
        tournament_type=tournament_type,
        registration_deadline=window.close_at_utc,
    )
    if tournament is not None:
        return tournament
    invite_code = await generate_invite_code(session)
    tournament = await TournamentsRepo.create(
        session,
        tournament=Tournament(
            id=uuid4(),
            type=tournament_type,
            created_by=None,
            name="Daily Arena Cup",
            status=TOURNAMENT_STATUS_REGISTRATION,
            format=TOURNAMENT_FORMAT_QUICK_5,
            max_participants=TOURNAMENT_MAX_PARTICIPANTS,
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
    await _emit_daily_cup_events(
        now_utc_value=now_utc_value,
        events=events,
        session_local=SessionLocal,
        emit_analytics_event=emit_analytics_event,
        event_source_worker=EVENT_SOURCE_WORKER,
    )


async def send_daily_cup_canceled_messages(
    *,
    telegram_targets: list[int],
    tournament_id: str | None = None,
    bot_factory: Callable[[], Any] | None = None,
) -> None:
    await _send_daily_cup_canceled_messages(
        telegram_targets=telegram_targets,
        tournament_id=tournament_id,
        bot_factory=bot_factory,
        operations=DailyCupCancelDeliveryOperations(
            default_bot_factory=build_bot,
            now_utc=now_utc,
            prepare_delivery=_prepare_daily_cup_cancel_delivery,
            begin_dispatch=_begin_daily_cup_cancel_dispatch,
            mark_failed=mark_telegram_delivery_failed,
            mark_sent=mark_telegram_delivery_sent,
            target_factory=_daily_cup_cancel_delivery_target,
        ),
    )


async def _prepare_daily_cup_cancel_delivery(*args: Any, **kwargs: Any) -> Any:
    return await prepare_telegram_delivery(*args, **kwargs)


async def _begin_daily_cup_cancel_dispatch(*args: Any, **kwargs: Any) -> None:
    await begin_telegram_delivery_dispatch(*args, **kwargs)


def _daily_cup_cancel_delivery_target(
    *,
    correlation_id: str,
    chat_id: int,
) -> TelegramDeliveryTarget:
    return daily_cup_cancel_delivery_target(
        correlation_id=correlation_id,
        chat_id=chat_id,
    )


async def persist_daily_cup_standings_message_ids(
    *,
    tournament_id: UUID,
    new_message_ids: dict[int, int],
    replaced_message_ids: dict[int, int],
) -> None:
    await _persist_daily_cup_standings_message_ids(
        tournament_id=tournament_id,
        new_message_ids=new_message_ids,
        replaced_message_ids=replaced_message_ids,
        session_local=SessionLocal,
        participants_repo=TournamentParticipantsRepo,
    )
