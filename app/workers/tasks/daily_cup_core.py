from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import text

from app.bot.application import build_bot
from app.bot.texts.de import TEXTS_DE
from app.core.analytics_events import EVENT_SOURCE_WORKER, emit_analytics_event
from app.db.models.tournaments import Tournament
from app.db.repo.production_reliability_types import TelegramDeliveryAttemptCreate
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import (
    TOURNAMENT_FORMAT_QUICK_5,
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_TYPE_DAILY_ARENA,
)
from app.game.tournaments.internal import generate_invite_code
from app.services.telegram_delivery import deliver_telegram_once
from app.workers.tasks.daily_cup_config import TOURNAMENT_MAX_PARTICIPANTS
from app.workers.tasks.daily_cup_time import get_daily_cup_window

logger = structlog.get_logger("app.workers.tasks.daily_cup_core")

_CANCEL_DELIVERY_PENDING_REPLAY_TTL_SECONDS = 300


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
    tournament_id: str,
    bot_factory: Callable[[], Any] | None = None,
    session_local: Any | None = None,
    deliver_once: Any | None = None,
) -> None:
    if not telegram_targets:
        return
    resolved_bot_factory = bot_factory if bot_factory is not None else build_bot
    resolved_session_local = session_local if session_local is not None else SessionLocal
    resolved_deliver_once = deliver_once if deliver_once is not None else deliver_telegram_once
    bot = resolved_bot_factory()
    try:
        for chat_id in telegram_targets:
            await _deliver_daily_cup_canceled_message(
                bot=bot,
                chat_id=chat_id,
                tournament_id=tournament_id,
                session_local=resolved_session_local,
                deliver_once=resolved_deliver_once,
            )
    finally:
        await bot.session.close()


async def _deliver_daily_cup_canceled_message(
    *,
    bot: Any,
    chat_id: int,
    tournament_id: str,
    session_local: Any,
    deliver_once: Any,
) -> None:
    async def _send() -> None:
        await bot.send_message(chat_id=chat_id, text=TEXTS_DE["msg.daily_cup.canceled"])

    try:
        await deliver_once(
            session_local,
            attempt=_daily_cup_cancel_attempt(tournament_id=tournament_id, chat_id=chat_id),
            send=_send,
            allow_stale_pending_replay_send=True,
            retry_claim_ttl_seconds=_CANCEL_DELIVERY_PENDING_REPLAY_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "daily_cup_cancel_delivery_failed",
            tournament_id=tournament_id,
            error_type=type(exc).__name__,
        )
        return


def _daily_cup_cancel_attempt(*, tournament_id: str, chat_id: int) -> TelegramDeliveryAttemptCreate:
    return TelegramDeliveryAttemptCreate(
        flow="daily_cup",
        task_name="daily_cup.cancel_delivery",
        correlation_id=f"daily_cup_cancel:{tournament_id}",
        idempotency_key=f"daily_cup:cancel:{tournament_id}:{chat_id}",
        target_type="daily_cup_cancel",
        target_id=tournament_id,
        telegram_user_id=chat_id,
    )


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
