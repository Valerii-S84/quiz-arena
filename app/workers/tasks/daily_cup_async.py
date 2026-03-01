from __future__ import annotations

from datetime import timedelta

import structlog
from aiogram.exceptions import TelegramForbiddenError

from app.bot.application import build_bot
from app.bot.keyboards.daily_cup import build_daily_cup_registration_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.repo.tournament_participants_repo import TournamentParticipantsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import (
    TOURNAMENT_STATUS_CANCELED,
    TOURNAMENT_STATUS_REGISTRATION,
    TOURNAMENT_STATUS_ROUND_1,
)
from app.game.tournaments.rounds import create_round_matches
from app.workers.tasks.daily_cup_config import (
    DAILY_CUP_ACTIVE_LOOKBACK_DAYS,
    DAILY_CUP_MIN_PARTICIPANTS,
    DAILY_CUP_PUSH_BATCH_SIZE,
)
from app.workers.tasks.daily_cup_core import (
    emit_daily_cup_events,
    ensure_daily_cup_registration_tournament,
    now_utc,
    round_deadline,
    send_daily_cup_canceled_messages,
)
from app.workers.tasks.daily_cup_messaging import enqueue_daily_cup_round_messaging
from app.workers.tasks.daily_cup_time import format_close_time_local

logger = structlog.get_logger("app.workers.tasks.daily_cup")


def _now_utc():
    return now_utc()


async def open_daily_cup_registration_async() -> dict[str, int]:
    now_utc_value = _now_utc()
    lookback_start = now_utc_value - timedelta(days=DAILY_CUP_ACTIVE_LOOKBACK_DAYS)

    async with SessionLocal.begin() as session:
        tournament = await ensure_daily_cup_registration_tournament(
            session=session, now_utc_value=now_utc_value
        )

    if tournament.status != TOURNAMENT_STATUS_REGISTRATION:
        return {"processed": 0, "users_scanned_total": 0, "sent_total": 0, "skipped_total": 0}

    scanned_total = sent_total = skipped_total = 0
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
    now_utc_value = _now_utc()
    canceled_telegram_targets: list[int] = []
    started_tournament_id: str | None = None
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
        if participants_total < DAILY_CUP_MIN_PARTICIPANTS:
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
            next_round_deadline = round_deadline(now_utc_value=now_utc_value)
            await create_round_matches(
                session,
                tournament=tournament,
                round_no=1,
                participants=participants,
                previous_pairs=set(),
                bye_history=set(),
                deadline=next_round_deadline,
                now_utc=now_utc_value,
            )
            tournament.current_round = 1
            tournament.status = TOURNAMENT_STATUS_ROUND_1
            tournament.round_deadline = next_round_deadline
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
    await send_daily_cup_canceled_messages(telegram_targets=canceled_telegram_targets)

    if started_tournament_id is not None:
        enqueue_daily_cup_round_messaging(tournament_id=started_tournament_id)
    return {
        "processed": 1,
        "canceled": canceled,
        "started": started,
        "participants_total": participants_total,
    }
