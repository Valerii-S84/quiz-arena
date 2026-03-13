from __future__ import annotations

import structlog

from app.bot.application import build_bot
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import (
    TOURNAMENT_STATUS_CANCELED,
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_TYPE_DAILY_ARENA,
)
from app.workers.tasks.daily_cup_config import (
    TOURNAMENT_MIN_PARTICIPANTS,
)
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


async def close_daily_cup_registration_and_start_async() -> dict[str, int]:
    now_utc_value = _now_utc()
    canceled_telegram_targets: list[int] = []
    started_tournament_id: str | None = None
    enqueue_legacy_round_messaging = False
    events: list[dict[str, object]] = []
    participants_total = canceled = started = 0

    async with SessionLocal.begin() as session:
        tournament = await ensure_daily_cup_registration_tournament(
            session=session, now_utc_value=now_utc_value
        )
        if tournament.status != TOURNAMENT_STATUS_REGISTRATION:
            return {"processed": 0, "canceled": 0, "started": 0, "participants_total": 0}

        participants = await TournamentParticipantsRepo.list_for_tournament_for_update(
            session,
            tournament_id=tournament.id,
        )
        participants_total = len(participants)
        if participants_total < TOURNAMENT_MIN_PARTICIPANTS:
            tournament.status = TOURNAMENT_STATUS_CANCELED
            tournament.round_deadline = None
            users = await UsersRepo.list_by_ids(
                session, [int(item.user_id) for item in participants]
            )
            canceled_telegram_targets = [int(user.telegram_user_id) for user in users]
            canceled = 1
            events.append(
                {
                    "event_type": "daily_cup_canceled",
                    "payload": {
                        "tournament_id": str(tournament.id),
                        "registered_total": participants_total,
                    },
                }
            )
        else:
            await start_daily_arena_round_one(
                session,
                tournament=tournament,
                participants=participants,
                now_utc=now_utc_value,
            )
            enqueue_legacy_round_messaging = True
            started_tournament_id = str(tournament.id)
            started = 1
            events.extend(
                [
                    {
                        "event_type": "daily_cup_started",
                        "payload": {
                            "tournament_id": started_tournament_id,
                            "participants_total": participants_total,
                        },
                    },
                    {
                        "event_type": "daily_cup_round_started",
                        "payload": {"tournament_id": started_tournament_id, "round_no": 1},
                    },
                ]
            )

    await emit_daily_cup_events(now_utc_value=now_utc_value, events=events)
    await send_daily_cup_canceled_messages(
        telegram_targets=canceled_telegram_targets, bot_factory=build_bot
    )
    if started_tournament_id is not None and enqueue_legacy_round_messaging:
        enqueue_daily_cup_round_messaging(tournament_id=started_tournament_id)
    return {
        "processed": 1,
        "canceled": canceled,
        "started": started,
        "participants_total": participants_total,
    }
