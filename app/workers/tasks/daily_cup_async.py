from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.application import build_bot
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import TOURNAMENT_STATUS_CANCELED, TOURNAMENT_TYPE_DAILY_ARENA
from app.workers.tasks.daily_cup_config import DAILY_CUP_MIN_PARTICIPANTS
from app.workers.tasks.daily_cup_core import (
    emit_daily_cup_events,
    ensure_daily_cup_registration_tournament,
    now_utc,
    send_daily_cup_canceled_messages,
)
from app.workers.tasks.daily_cup_messaging import (
    enqueue_daily_cup_round_messaging,
    run_daily_cup_round_messaging_async_with_followups,
)
from app.workers.tasks.daily_cup_registration_close import (
    DailyCupCloseTransition as _DailyCupCloseTransition,
)
from app.workers.tasks.daily_cup_registration_close import (
    DailyCupRegistrationCloseDependencies,
    build_close_transition,
)
from app.workers.tasks.daily_cup_registration_push import send_daily_cup_registration_push_async
from app.workers.tasks.daily_cup_start import start_daily_arena_round_one
from app.workers.tasks.daily_cup_time import get_daily_cup_window

logger = structlog.get_logger("app.workers.tasks.daily_cup")

_now_utc = now_utc


async def send_daily_cup_invite_registration_async() -> dict[str, int]:
    return await send_daily_cup_registration_push_async(
        now_utc_factory=_now_utc,
        bot_factory=build_bot,
        text_key="msg.daily_cup.push.registration",
        log_event="daily_cup_invite_registration_push_processed",
        sent_event_type="daily_cup_invite_registration_push_sent",
        logger=logger,
    )


async def send_daily_cup_invite_async() -> dict[str, int]:
    return await send_daily_cup_invite_registration_async()


async def open_daily_cup_registration_async() -> dict[str, int]:
    return await send_daily_cup_invite_registration_async()


async def send_daily_cup_last_call_reminder_async() -> dict[str, int]:
    return await send_daily_cup_registration_push_async(
        now_utc_factory=_now_utc,
        bot_factory=build_bot,
        text_key="msg.daily_cup.last_call_reminder",
        log_event="daily_cup_last_call_reminder_processed",
        sent_event_type="daily_cup_last_call_reminder_sent",
        logger=logger,
    )


async def publish_daily_cup_final_results_async() -> dict[str, int]:
    now_utc_value = _now_utc()
    async with SessionLocal.begin() as session:
        tournament = await TournamentsRepo.get_by_type_and_registration_deadline(
            session,
            tournament_type=TOURNAMENT_TYPE_DAILY_ARENA,
            registration_deadline=get_daily_cup_window(now_utc=now_utc_value).close_at_utc,
        )
        if tournament is None or tournament.status != "COMPLETED":
            return {"processed": 0, "published": 0}
        tournament_id = str(tournament.id)
    result = await run_daily_cup_round_messaging_async_with_followups(
        tournament_id=tournament_id,
        enqueue_completion_followups=True,
    )
    return {"processed": 1, "published": int(result.get("processed", 0) > 0)}


async def _build_close_transition(
    *,
    session,
    tournament,
    now_utc_value,
) -> _DailyCupCloseTransition | None:
    return await build_close_transition(
        session=session,
        tournament=tournament,
        now_utc_value=now_utc_value,
        minimum_participants=DAILY_CUP_MIN_PARTICIPANTS,
        dependencies=DailyCupRegistrationCloseDependencies(
            list_participants_for_update=TournamentParticipantsRepo.list_for_tournament_for_update,
            list_users_by_ids=UsersRepo.list_by_ids,
            start_round_one=start_daily_arena_round_one,
        ),
    )


async def _load_close_tournament(
    *,
    session: AsyncSession,
    now_utc_value,
    tournament_id: str | None,
) -> Tournament | None:
    if tournament_id is None:
        return await ensure_daily_cup_registration_tournament(
            session=session,
            now_utc_value=now_utc_value,
        )
    try:
        parsed_tournament_id = UUID(tournament_id)
    except ValueError as exc:
        raise ValueError("invalid Daily Cup tournament id") from exc
    tournament = await TournamentsRepo.get_by_id_for_update(session, parsed_tournament_id)
    if (
        tournament is None
        or tournament.type != TOURNAMENT_TYPE_DAILY_ARENA
        or tournament.status != TOURNAMENT_STATUS_CANCELED
    ):
        return None
    return tournament


async def close_daily_cup_registration_and_start_async(
    *,
    tournament_id: str | None = None,
) -> dict[str, int]:
    now_utc_value = _now_utc()
    async with SessionLocal.begin() as session:
        tournament = await _load_close_tournament(
            session=session,
            now_utc_value=now_utc_value,
            tournament_id=tournament_id,
        )
        if tournament is None:
            return {"processed": 0, "canceled": 0, "started": 0, "participants_total": 0}
        transition = await _build_close_transition(
            session=session,
            tournament=tournament,
            now_utc_value=now_utc_value,
        )
        if transition is None:
            return {"processed": 0, "canceled": 0, "started": 0, "participants_total": 0}

    await emit_daily_cup_events(now_utc_value=now_utc_value, events=transition.events)
    await send_daily_cup_canceled_messages(
        telegram_targets=transition.canceled_telegram_targets,
        tournament_id=transition.tournament_id,
        bot_factory=build_bot,
    )
    if transition.started_tournament_id is not None:
        enqueue_daily_cup_round_messaging(tournament_id=transition.started_tournament_id)
    return {
        "processed": 1,
        "canceled": transition.canceled,
        "started": transition.started,
        "participants_total": transition.participants_total,
    }
