from __future__ import annotations

from datetime import timedelta

import structlog

from app.bot.application import build_bot
from app.bot.keyboards.daily_cup import build_daily_cup_lobby_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.friend_challenges.constants import DUEL_STATUS_CREATOR_DONE, DUEL_STATUS_OPPONENT_DONE
from app.game.tournaments.constants import TOURNAMENT_SELF_BOT_LABEL
from app.workers.tasks.daily_cup_config import (
    DAILY_CUP_PUSH_BATCH_SIZE,
    DAILY_CUP_TURN_REMINDER_INTERVAL_MINUTES,
)
from app.workers.tasks.daily_cup_core import now_utc
from app.workers.tasks.daily_cup_push_events import store_push_sent_events
from app.workers.tasks.daily_cup_turn_reminder_delivery import (
    deliver_reminders,
    prepare_reminder_batch,
)
from app.workers.tasks.daily_cup_turn_reminder_events import store_reminder_events
from app.workers.tasks.tournaments_messaging_text import format_deadline, format_user_label

logger = structlog.get_logger("app.workers.tasks.daily_cup_turn_reminder")

_REMINDER_EVENT_TYPE = "daily_cup_turn_reminder_sent"


def resolve_turn_reminder_users(*, challenge: FriendChallenge) -> tuple[tuple[int, int], ...]:
    if challenge.opponent_user_id is None:
        return ()
    creator_user_id = int(challenge.creator_user_id)
    opponent_user_id = int(challenge.opponent_user_id)
    if challenge.status == DUEL_STATUS_CREATOR_DONE:
        return ((opponent_user_id, creator_user_id),)
    if challenge.status == DUEL_STATUS_OPPONENT_DONE:
        return ((creator_user_id, opponent_user_id),)
    if challenge.status == "ACCEPTED":
        return (
            (creator_user_id, opponent_user_id),
            (opponent_user_id, creator_user_id),
        )
    return ()


def _build_turn_reminder_text(*, opponent_label: str, deadline_text: str) -> str:
    return TEXTS_DE["msg.daily_cup.turn_reminder"].format(
        opponent_label=opponent_label,
        deadline=deadline_text,
    )


def _resolve_turn_reminder_opponent_label(
    *,
    target_user_id: int,
    opponent_user_id: int,
    user_labels: dict[int, str],
) -> str:
    if target_user_id == opponent_user_id:
        return TOURNAMENT_SELF_BOT_LABEL
    return user_labels.get(opponent_user_id, "Spieler")


def _build_turn_reminder_result(
    *,
    batch_size: int,
    scanned_total: int,
    queued_total: int,
    sent_total: int,
    skipped_total: int,
    failed_total: int,
) -> dict[str, int]:
    return {
        "processed": 1,
        "batch_size": batch_size,
        "scanned_total": scanned_total,
        "queued_total": queued_total,
        "sent_total": sent_total,
        "skipped_total": skipped_total,
        "failed_total": failed_total,
    }


async def _load_reminder_batch(
    *,
    now_utc_value,
    remind_before_utc,
    resolved_batch_size: int,
):
    async with SessionLocal.begin() as session:
        candidates = await TournamentMatchesRepo.list_daily_cup_turn_reminder_candidates_for_update(
            session,
            now_utc=now_utc_value,
            remind_before_utc=remind_before_utc,
            limit=resolved_batch_size,
        )
        if not candidates:
            return None
        return await prepare_reminder_batch(
            candidates=candidates,
            now_utc_value=now_utc_value,
            format_user_label_fn=format_user_label,
            list_users_by_ids=UsersRepo.list_by_ids,
            session=session,
            resolve_turn_reminder_users_fn=resolve_turn_reminder_users,
            resolve_opponent_label_fn=_resolve_turn_reminder_opponent_label,
            format_deadline_fn=format_deadline,
        )


async def run_daily_cup_turn_reminders_async(
    *, batch_size: int = DAILY_CUP_PUSH_BATCH_SIZE
) -> dict[str, int]:
    now_utc_value = now_utc()
    remind_before_utc = now_utc_value - timedelta(minutes=DAILY_CUP_TURN_REMINDER_INTERVAL_MINUTES)
    resolved_batch_size = max(1, int(batch_size))

    scanned_total = sent_total = skipped_total = failed_total = 0
    queued_total = 0
    batch = await _load_reminder_batch(
        now_utc_value=now_utc_value,
        remind_before_utc=remind_before_utc,
        resolved_batch_size=resolved_batch_size,
    )
    if batch is None:
        result = _build_turn_reminder_result(
            batch_size=resolved_batch_size,
            scanned_total=0,
            queued_total=0,
            sent_total=0,
            skipped_total=0,
            failed_total=0,
        )
        logger.info("daily_cup_turn_reminders_processed", **result)
        return result
    scanned_total = batch.scanned_total
    skipped_total = batch.skipped_total
    queued_total = len(batch.reminders)

    delivery_result = await deliver_reminders(
        reminders=batch.reminders,
        build_bot_fn=build_bot,
        build_keyboard=build_daily_cup_lobby_keyboard,
        build_text=_build_turn_reminder_text,
        logger=logger,
    )
    sent_total = delivery_result.sent_total
    failed_total = delivery_result.failed_total
    skipped_total += delivery_result.skipped_total
    await store_reminder_events(
        sent_user_ids_by_tournament=delivery_result.sent_user_ids_by_tournament,
        event_type=_REMINDER_EVENT_TYPE,
        happened_at=now_utc_value,
        store_push_sent_events_fn=store_push_sent_events,
        logger=logger,
    )

    result = _build_turn_reminder_result(
        batch_size=resolved_batch_size,
        scanned_total=scanned_total,
        queued_total=queued_total,
        sent_total=sent_total,
        skipped_total=skipped_total,
        failed_total=failed_total,
    )
    logger.info("daily_cup_turn_reminders_processed", **result)
    return result


__all__ = ["resolve_turn_reminder_users", "run_daily_cup_turn_reminders_async"]
