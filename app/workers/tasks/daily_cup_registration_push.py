from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.bot.application import build_bot
from app.bot.keyboards.daily_cup import build_daily_cup_registration_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import TOURNAMENT_STATUS_REGISTRATION
from app.services.telegram_delivery import (
    SKIP_CODE_DUPLICATE,
    TelegramDeliveryTarget,
    begin_telegram_delivery_dispatch,
    mark_telegram_delivery_failed,
    prepare_telegram_delivery,
    record_telegram_delivery_skipped,
)
from app.workers.tasks.daily_cup_config import (
    DAILY_CUP_ACTIVE_LOOKBACK_DAYS,
    DAILY_CUP_PUSH_BATCH_SIZE,
)
from app.workers.tasks.daily_cup_core import ensure_daily_cup_registration_tournament
from app.workers.tasks.daily_cup_push_events import list_already_pushed_user_ids
from app.workers.tasks.daily_cup_registration_push_delivery import (
    DailyCupRegistrationPushOperations,
    DailyCupRegistrationPushRun,
    send_daily_cup_registration_push_once,
)
from app.workers.tasks.daily_cup_registration_push_outcome import (
    record_daily_cup_registration_push_sent,
)
from app.workers.tasks.daily_cup_registration_push_targets import daily_cup_delivery_target
from app.workers.tasks.daily_cup_time import format_close_time_local


async def _prepare_registration_push_delivery(*args: Any, **kwargs: Any) -> Any:
    return await prepare_telegram_delivery(*args, **kwargs)


async def _begin_registration_push_dispatch(*args: Any, **kwargs: Any) -> None:
    await begin_telegram_delivery_dispatch(*args, **kwargs)


async def _send_daily_cup_registration_push_once(
    *,
    run: DailyCupRegistrationPushRun,
    target: TelegramDeliveryTarget,
    user_id: int,
) -> bool:
    return await send_daily_cup_registration_push_once(
        run=run,
        target=target,
        user_id=user_id,
        operations=DailyCupRegistrationPushOperations(
            prepare_delivery=_prepare_registration_push_delivery,
            begin_dispatch=_begin_registration_push_dispatch,
            mark_failed=mark_telegram_delivery_failed,
            record_sent=record_daily_cup_registration_push_sent,
            build_keyboard=build_daily_cup_registration_keyboard,
        ),
    )


async def _send_daily_cup_registration_push_batches(
    *,
    run: DailyCupRegistrationPushRun,
    tournament_id: Any,
    lookback_start: datetime,
) -> tuple[int, int, int]:
    scanned_total = sent_total = skipped_total = 0
    last_user_id: int | None = None
    while True:
        async with SessionLocal.begin() as session:
            targets = await UsersRepo.list_daily_cup_push_targets(
                session,
                tournament_id=tournament_id,
                active_since_utc=lookback_start,
                after_user_id=last_user_id,
                limit=DAILY_CUP_PUSH_BATCH_SIZE,
            )
        if not targets:
            break

        already_pushed_user_ids = await list_already_pushed_user_ids(
            event_type=run.sent_event_type,
            tournament_id=run.tournament_id_text,
            user_ids=[user_id for user_id, _telegram_user_id in targets],
        )
        for user_id, telegram_user_id in targets:
            scanned_total += 1
            last_user_id = user_id
            target = daily_cup_delivery_target(
                flow=run.flow,
                task_name=run.task_name,
                tournament_id_text=run.tournament_id_text,
                user_id=user_id,
                telegram_user_id=telegram_user_id,
            )
            if user_id in already_pushed_user_ids:
                await record_telegram_delivery_skipped(
                    target=target,
                    happened_at=run.happened_at,
                    failure_code=SKIP_CODE_DUPLICATE,
                    failure_reason="daily cup analytics sent event already exists",
                )
                skipped_total += 1
                continue
            if await _send_daily_cup_registration_push_once(
                run=run,
                target=target,
                user_id=user_id,
            ):
                sent_total += 1
            else:
                skipped_total += 1
    return scanned_total, sent_total, skipped_total


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

    tournament_id_text = str(tournament.id)
    flow = sent_event_type.removesuffix("_sent")
    task_name = log_event.removesuffix("_processed")
    close_time_label = format_close_time_local(close_at_utc=tournament.registration_deadline)
    text = TEXTS_DE[text_key].format(close_time=close_time_label)

    bot = bot_factory()
    run = DailyCupRegistrationPushRun(
        bot=bot,
        logger=logger,
        flow=flow,
        task_name=task_name,
        text=text,
        tournament_id_text=tournament_id_text,
        happened_at=now_utc_value,
        sent_event_type=sent_event_type,
    )
    try:
        scanned_total, sent_total, skipped_total = await _send_daily_cup_registration_push_batches(
            run=run,
            tournament_id=tournament.id,
            lookback_start=lookback_start,
        )
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
