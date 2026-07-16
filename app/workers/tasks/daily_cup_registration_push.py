from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.bot.application import build_bot
from app.bot.keyboards.daily_cup import build_daily_cup_registration_keyboard
from app.bot.texts.de import TEXTS_DE
from app.core.analytics_events import BERLIN_TIMEZONE, EVENT_SOURCE_WORKER
from app.db.repo.analytics_repo import AnalyticsRepo
from app.db.repo.production_reliability_types import TelegramDeliveryAttemptCreate
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import TOURNAMENT_STATUS_REGISTRATION
from app.services.telegram_delivery import deliver_telegram_once
from app.workers.tasks.daily_cup_config import (
    DAILY_CUP_ACTIVE_LOOKBACK_DAYS,
    DAILY_CUP_PUSH_BATCH_SIZE,
)
from app.workers.tasks.daily_cup_core import ensure_daily_cup_registration_tournament
from app.workers.tasks.daily_cup_push_events import list_already_pushed_user_ids
from app.workers.tasks.daily_cup_time import format_close_time_local


@dataclass(frozen=True, slots=True)
class _RegistrationPushItem:
    user_id: int
    telegram_user_id: int
    text: str
    tournament_id_text: str
    happened_at: Any
    sent_event_type: str


def _registration_push_attempt(item: _RegistrationPushItem) -> TelegramDeliveryAttemptCreate:
    return TelegramDeliveryAttemptCreate(
        flow="daily_cup",
        task_name=f"daily_cup.{item.sent_event_type}",
        correlation_id=f"daily_cup_registration:{item.tournament_id_text}",
        idempotency_key=(
            f"daily_cup:{item.sent_event_type}:{item.tournament_id_text}:{item.user_id}"
        ),
        target_type="daily_cup_registration_push",
        target_id=item.tournament_id_text,
        telegram_user_id=item.telegram_user_id,
        safe_context={"event_type": item.sent_event_type, "user_id": item.user_id},
    )


async def _store_daily_cup_registration_push_event_once(item: _RegistrationPushItem) -> bool:
    async with SessionLocal.begin() as session:
        return await AnalyticsRepo.create_daily_cup_push_event_once(
            session,
            event_type=item.sent_event_type,
            source=EVENT_SOURCE_WORKER,
            user_id=item.user_id,
            local_date_berlin=item.happened_at.astimezone(ZoneInfo(BERLIN_TIMEZONE)).date(),
            payload={"tournament_id": item.tournament_id_text},
            happened_at=item.happened_at,
        )


async def _send_registration_push_message(*, bot: Any, item: _RegistrationPushItem) -> None:
    await bot.send_message(
        chat_id=item.telegram_user_id,
        text=item.text,
        reply_markup=build_daily_cup_registration_keyboard(tournament_id=item.tournament_id_text),
    )


async def _send_daily_cup_registration_push_once(
    *,
    bot,
    logger,
    item: _RegistrationPushItem,
) -> bool:
    async def _send() -> None:
        await _send_registration_push_message(bot=bot, item=item)

    try:
        outcome = await deliver_telegram_once(
            SessionLocal,
            attempt=_registration_push_attempt(item),
            send=_send,
        )
    except Exception as exc:
        logger.warning(
            "daily_cup_registration_push_send_failed",
            event_type=item.sent_event_type,
            tournament_id=item.tournament_id_text,
            user_id=item.user_id,
            error_type=type(exc).__name__,
        )
        return False
    if outcome.status != "SENT":
        return False
    try:
        await _store_daily_cup_registration_push_event_once(item)
    except Exception as exc:
        logger.warning(
            "daily_cup_registration_push_event_store_failed",
            event_type=item.sent_event_type,
            tournament_id=item.tournament_id_text,
            user_id=item.user_id,
            error_type=type(exc).__name__,
        )
    return True


async def send_daily_cup_registration_push_async(
    *,
    now_utc_factory,
    bot_factory=build_bot,
    text_key: str,
    log_event: str,
    sent_event_type: str,
    logger,
) -> dict[str, int]:
    now_utc_value = now_utc_factory()
    lookback_start = now_utc_value - timedelta(days=DAILY_CUP_ACTIVE_LOOKBACK_DAYS)

    async with SessionLocal.begin() as session:
        tournament = await ensure_daily_cup_registration_tournament(
            session=session,
            now_utc_value=now_utc_value,
        )

    if tournament.status != TOURNAMENT_STATUS_REGISTRATION:
        return {"processed": 0, "users_scanned_total": 0, "sent_total": 0, "skipped_total": 0}

    scanned_total = sent_total = skipped_total = 0
    last_user_id: int | None = None
    tournament_id_text = str(tournament.id)
    close_time_label = format_close_time_local(close_at_utc=tournament.registration_deadline)
    text = TEXTS_DE[text_key].format(close_time=close_time_label)

    bot = bot_factory()
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

            target_user_ids = [user_id for user_id, _telegram_user_id in targets]
            already_pushed_user_ids = await list_already_pushed_user_ids(
                event_type=sent_event_type,
                tournament_id=tournament_id_text,
                user_ids=target_user_ids,
            )
            for user_id, telegram_user_id in targets:
                scanned_total += 1
                last_user_id = user_id
                if user_id in already_pushed_user_ids:
                    skipped_total += 1
                    continue
                if await _send_daily_cup_registration_push_once(
                    bot=bot,
                    logger=logger,
                    item=_RegistrationPushItem(
                        user_id=user_id,
                        telegram_user_id=telegram_user_id,
                        text=text,
                        tournament_id_text=tournament_id_text,
                        happened_at=now_utc_value,
                        sent_event_type=sent_event_type,
                    ),
                ):
                    sent_total += 1
                else:
                    skipped_total += 1
    finally:
        await bot.session.close()

    result = {
        "processed": 1,
        "users_scanned_total": scanned_total,
        "sent_total": sent_total,
        "skipped_total": skipped_total,
    }
    logger.info(log_event, **result)
    return result
