from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import structlog
from aiogram.exceptions import TelegramForbiddenError

from app.bot.application import build_bot
from app.bot.keyboards.daily_cup import build_daily_cup_registration_keyboard
from app.bot.texts.de import TEXTS_DE
from app.core.analytics_events import EVENT_SOURCE_WORKER, emit_analytics_event
from app.db.models.tournaments import Tournament
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import (
    TOURNAMENT_FORMAT_QUICK_5,
    TOURNAMENT_STATUS_CANCELED,
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_STATUS_ROUND_1,
    TOURNAMENT_TYPE_DAILY_ARENA,
)
from app.game.tournaments.internal import generate_invite_code
from app.game.tournaments.rounds import create_round_matches
from app.workers.tasks.daily_cup_config import (
    DAILY_CUP_ACTIVE_LOOKBACK_DAYS,
    DAILY_CUP_MIN_PARTICIPANTS,
    DAILY_CUP_PUSH_BATCH_SIZE,
    DAILY_CUP_ROUND_DURATION_MINUTES,
)
from app.workers.tasks.daily_cup_messaging import enqueue_daily_cup_round_messaging
from app.workers.tasks.daily_cup_time import format_close_time_local, get_daily_cup_window

logger = structlog.get_logger("app.workers.tasks.daily_cup")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _round_deadline(*, now_utc: datetime) -> datetime:
    return now_utc + timedelta(minutes=max(1, int(DAILY_CUP_ROUND_DURATION_MINUTES)))


async def _ensure_daily_cup_registration_tournament(
    *,
    session,
    now_utc: datetime,
) -> Tournament:
    window = get_daily_cup_window(now_utc=now_utc)
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
            created_at=now_utc,
        ),
    )
    return tournament


async def _emit_daily_cup_events(*, now_utc: datetime, events: list[dict[str, object]]) -> None:
    if not events:
        return
    async with SessionLocal.begin() as session:
        for event in events:
            payload_raw = event.get("payload")
            await emit_analytics_event(
                session,
                event_type=str(event["event_type"]),
                source=EVENT_SOURCE_WORKER,
                happened_at=now_utc,
                user_id=None,
                payload=(payload_raw if isinstance(payload_raw, dict) else {}),
            )


async def open_daily_cup_registration_async() -> dict[str, int]:
    now_utc = _now_utc()
    lookback_start = now_utc - timedelta(days=DAILY_CUP_ACTIVE_LOOKBACK_DAYS)

    async with SessionLocal.begin() as session:
        tournament = await _ensure_daily_cup_registration_tournament(session=session, now_utc=now_utc)

    if tournament.status != TOURNAMENT_STATUS_REGISTRATION:
        return {"processed": 0, "users_scanned_total": 0, "sent_total": 0, "skipped_total": 0}

    scanned_total = 0
    sent_total = 0
    skipped_total = 0
    last_user_id: int | None = None
    close_time_label = format_close_time_local(close_at_utc=tournament.registration_deadline)
    text = TEXTS_DE["msg.daily_cup.push.registration"].format(close_time=close_time_label)

    bot = build_bot()
    try:
        while True:
            async with SessionLocal.begin() as session:
                targets = await UsersRepo.list_daily_cup_push_targets(
                    session,
                    tournament_id=tournament.id,
                    active_since_utc=lookback_start,
                    after_user_id=last_user_id,
                    limit=DAILY_CUP_PUSH_BATCH_SIZE,
                )
            if not targets:
                break
            for user_id, telegram_user_id in targets:
                scanned_total += 1
                last_user_id = user_id
                try:
                    await bot.send_message(
                        chat_id=telegram_user_id,
                        text=text,
                        reply_markup=build_daily_cup_registration_keyboard(
                            tournament_id=str(tournament.id)
                        ),
                    )
                    sent_total += 1
                except TelegramForbiddenError:
                    skipped_total += 1
                except Exception:
                    skipped_total += 1
    finally:
        await bot.session.close()

    result = {
        "processed": 1,
        "users_scanned_total": scanned_total,
        "sent_total": sent_total,
        "skipped_total": skipped_total,
    }
    logger.info("daily_cup_registration_push_processed", **result)
    return result


async def close_daily_cup_registration_and_start_async() -> dict[str, int]:
    now_utc = _now_utc()
    canceled_telegram_targets: list[int] = []
    started_tournament_id: str | None = None
    events: list[dict[str, object]] = []
    participants_total = 0
    canceled = 0
    started = 0

    async with SessionLocal.begin() as session:
        tournament = await _ensure_daily_cup_registration_tournament(session=session, now_utc=now_utc)
        if tournament.status != TOURNAMENT_STATUS_REGISTRATION:
            return {"processed": 0, "canceled": 0, "started": 0, "participants_total": 0}

        participants = await TournamentParticipantsRepo.list_for_tournament_for_update(
            session,
            tournament_id=tournament.id,
        )
        participants_total = len(participants)
        if participants_total < DAILY_CUP_MIN_PARTICIPANTS:
            tournament.status = TOURNAMENT_STATUS_CANCELED
            tournament.round_deadline = None
            users = await UsersRepo.list_by_ids(session, [int(item.user_id) for item in participants])
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
            round_deadline = _round_deadline(now_utc=now_utc)
            await create_round_matches(
                session,
                tournament=tournament,
                round_no=1,
                participants=participants,
                previous_pairs=set(),
                bye_history=set(),
                deadline=round_deadline,
                now_utc=now_utc,
            )
            tournament.current_round = 1
            tournament.status = TOURNAMENT_STATUS_ROUND_1
            tournament.round_deadline = round_deadline
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

    await _emit_daily_cup_events(now_utc=now_utc, events=events)

    if canceled_telegram_targets:
        bot = build_bot()
        try:
            for chat_id in canceled_telegram_targets:
                try:
                    await bot.send_message(chat_id=chat_id, text=TEXTS_DE["msg.daily_cup.canceled"])
                except TelegramForbiddenError:
                    continue
                except Exception:
                    continue
        finally:
            await bot.session.close()

    if started_tournament_id is not None:
        enqueue_daily_cup_round_messaging(tournament_id=started_tournament_id)
    return {
        "processed": 1,
        "canceled": canceled,
        "started": started,
        "participants_total": participants_total,
    }
