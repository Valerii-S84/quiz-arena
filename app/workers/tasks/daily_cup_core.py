from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

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
from app.services.telegram_delivery import (
    TelegramDeliveryTarget,
    begin_telegram_delivery_dispatch,
    build_delivery_idempotency_key,
    hash_chat_id,
    mark_telegram_delivery_failed,
    mark_telegram_delivery_sent,
    prepare_telegram_delivery,
)
from app.workers.tasks.daily_cup_config import TOURNAMENT_MAX_PARTICIPANTS
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
    tournament_id: str | None = None,
    bot_factory: Callable[[], Any] | None = None,
) -> None:
    if not telegram_targets:
        return
    resolved_bot_factory = bot_factory if bot_factory is not None else build_bot
    bot = resolved_bot_factory()
    happened_at = now_utc()
    correlation_id = tournament_id or "unknown"
    try:
        for chat_id in telegram_targets:
            target = _daily_cup_cancel_delivery_target(
                correlation_id=correlation_id,
                chat_id=chat_id,
            )
            delivery = await prepare_telegram_delivery(target=target, happened_at=happened_at)
            if not delivery.should_send:
                continue
            await begin_telegram_delivery_dispatch(delivery, happened_at=happened_at)
            try:
                await bot.send_message(chat_id=chat_id, text=TEXTS_DE["msg.daily_cup.canceled"])
            except Exception as exc:
                await mark_telegram_delivery_failed(
                    idempotency_key=target.idempotency_key,
                    happened_at=happened_at,
                    exc=exc,
                )
                continue
            await mark_telegram_delivery_sent(
                idempotency_key=target.idempotency_key,
                happened_at=happened_at,
            )
    finally:
        await bot.session.close()


def _daily_cup_cancel_delivery_target(
    *,
    correlation_id: str,
    chat_id: int,
) -> TelegramDeliveryTarget:
    content_version = "status:canceled"
    target_id = f"{hash_chat_id(chat_id)}:{content_version}"
    return TelegramDeliveryTarget(
        flow="daily_cup_cancel_message",
        task_name="daily_cup.close_registration_and_start",
        correlation_id=correlation_id,
        target_type="chat_hash",
        target_id=target_id,
        idempotency_key=build_delivery_idempotency_key(
            flow="daily_cup_cancel_message",
            correlation_id=correlation_id,
            target_type="chat_hash",
            target_id=target_id,
        ),
        telegram_user_id=chat_id,
        chat_id=chat_id,
        safe_context={
            "tournament_id": correlation_id,
            "content_version": content_version,
            "pending_replay_safe": False,
        },
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
