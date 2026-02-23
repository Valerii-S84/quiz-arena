from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog

from app.bot.application import build_bot
from app.bot.keyboards.friend_challenge import (
    build_friend_challenge_finished_keyboard,
    build_friend_challenge_next_keyboard,
)
from app.core.analytics_events import EVENT_SOURCE_WORKER, emit_analytics_event
from app.core.config import get_settings
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.workers.asyncio_runner import run_async_job
from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)
settings = get_settings()

DEADLINE_BATCH_SIZE = max(1, int(settings.friend_challenge_deadline_batch_size))
LAST_CHANCE_SECONDS = max(60, int(settings.friend_challenge_last_chance_seconds))
SCAN_INTERVAL_SECONDS = max(30, int(settings.friend_challenge_deadline_scan_interval_seconds))


def _format_remaining_hhmm(*, now_utc: datetime, expires_at: datetime) -> tuple[int, int]:
    remaining_seconds = max(0, int((expires_at - now_utc).total_seconds()))
    return remaining_seconds // 3600, (remaining_seconds % 3600) // 60


async def _resolve_telegram_targets(user_ids: set[int]) -> dict[int, int]:
    if not user_ids:
        return {}
    async with SessionLocal.begin() as session:
        users = await UsersRepo.list_by_ids(session, list(user_ids))
    return {int(user.id): int(user.telegram_user_id) for user in users}


async def run_friend_challenge_deadlines_async(
    *, batch_size: int = DEADLINE_BATCH_SIZE
) -> dict[str, int]:
    now_utc = datetime.now(timezone.utc)
    expires_before_utc = now_utc + timedelta(seconds=LAST_CHANCE_SECONDS)
    resolved_batch_size = max(1, int(batch_size))

    reminder_items: list[dict[str, object]] = []
    expired_items: list[dict[str, object]] = []

    async with SessionLocal.begin() as session:
        due_last_chance = await FriendChallengesRepo.list_active_due_for_last_chance_for_update(
            session,
            now_utc=now_utc,
            expires_before_utc=expires_before_utc,
            limit=resolved_batch_size,
        )
        for challenge in due_last_chance:
            challenge.expires_last_chance_notified_at = now_utc
            challenge.updated_at = now_utc
            reminder_items.append(
                {
                    "challenge_id": str(challenge.id),
                    "creator_user_id": int(challenge.creator_user_id),
                    "opponent_user_id": (
                        int(challenge.opponent_user_id)
                        if challenge.opponent_user_id is not None
                        else None
                    ),
                    "expires_at": challenge.expires_at,
                }
            )

        due_expired = await FriendChallengesRepo.list_active_due_for_expire_for_update(
            session,
            now_utc=now_utc,
            limit=resolved_batch_size,
        )
        for challenge in due_expired:
            challenge.status = "EXPIRED"
            challenge.winner_user_id = None
            challenge.completed_at = now_utc
            challenge.updated_at = now_utc
            expired_items.append(
                {
                    "challenge_id": str(challenge.id),
                    "creator_user_id": int(challenge.creator_user_id),
                    "opponent_user_id": (
                        int(challenge.opponent_user_id)
                        if challenge.opponent_user_id is not None
                        else None
                    ),
                    "creator_score": int(challenge.creator_score),
                    "opponent_score": int(challenge.opponent_score),
                    "total_rounds": int(challenge.total_rounds),
                    "expires_at": challenge.expires_at,
                }
            )
            await emit_analytics_event(
                session,
                event_type="friend_challenge_expired",
                source=EVENT_SOURCE_WORKER,
                happened_at=now_utc,
                user_id=None,
                payload={
                    "challenge_id": str(challenge.id),
                    "creator_user_id": int(challenge.creator_user_id),
                    "opponent_user_id": (
                        int(challenge.opponent_user_id)
                        if challenge.opponent_user_id is not None
                        else None
                    ),
                    "creator_score": int(challenge.creator_score),
                    "opponent_score": int(challenge.opponent_score),
                    "total_rounds": int(challenge.total_rounds),
                    "expires_at": challenge.expires_at.isoformat(),
                },
            )

    user_ids: set[int] = set()
    for item in reminder_items:
        user_ids.add(int(item["creator_user_id"]))
        opponent_user_id = item["opponent_user_id"]
        if isinstance(opponent_user_id, int):
            user_ids.add(opponent_user_id)
    for item in expired_items:
        user_ids.add(int(item["creator_user_id"]))
        opponent_user_id = item["opponent_user_id"]
        if isinstance(opponent_user_id, int):
            user_ids.add(opponent_user_id)
    telegram_targets = await _resolve_telegram_targets(user_ids)

    reminders_sent = 0
    reminders_failed = 0
    expired_notices_sent = 0
    expired_notices_failed = 0
    reminder_events: list[dict[str, object]] = []
    expired_notice_events: list[dict[str, object]] = []

    bot = build_bot()
    try:
        for item in reminder_items:
            expires_at = item["expires_at"]
            if not isinstance(expires_at, datetime):
                continue
            hours, minutes = _format_remaining_hhmm(now_utc=now_utc, expires_at=expires_at)
            text = (
                f"⏳ Dein Duell läuft bald ab ({hours:02d}:{minutes:02d}h). " "Jetzt weiterspielen!"
            )
            challenge_id = str(item["challenge_id"])
            target_user_ids = [int(item["creator_user_id"])]
            opponent_user_id = item["opponent_user_id"]
            if isinstance(opponent_user_id, int):
                target_user_ids.append(opponent_user_id)

            sent_to = 0
            failed_to = 0
            for target_user_id in target_user_ids:
                telegram_user_id = telegram_targets.get(target_user_id)
                if telegram_user_id is None:
                    failed_to += 1
                    continue
                try:
                    await bot.send_message(
                        chat_id=telegram_user_id,
                        text=text,
                        reply_markup=build_friend_challenge_next_keyboard(
                            challenge_id=challenge_id
                        ),
                    )
                    sent_to += 1
                except Exception:
                    failed_to += 1

            reminders_sent += sent_to
            reminders_failed += failed_to
            reminder_events.append(
                {
                    "challenge_id": challenge_id,
                    "sent_to": sent_to,
                    "failed_to": failed_to,
                    "expires_at": expires_at.isoformat(),
                }
            )

        for item in expired_items:
            challenge_id = str(item["challenge_id"])
            creator_user_id = int(item["creator_user_id"])
            opponent_user_id = item["opponent_user_id"]
            creator_score = int(item["creator_score"])
            opponent_score = int(item["opponent_score"])

            sent_to = 0
            failed_to = 0

            creator_telegram = telegram_targets.get(creator_user_id)
            if creator_telegram is None:
                failed_to += 1
            else:
                try:
                    await bot.send_message(
                        chat_id=creator_telegram,
                        text=(
                            "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
                            f"Finaler Score: Du {creator_score} | Gegner {opponent_score}."
                        ),
                        reply_markup=build_friend_challenge_finished_keyboard(
                            challenge_id=challenge_id
                        ),
                    )
                    sent_to += 1
                except Exception:
                    failed_to += 1

            if isinstance(opponent_user_id, int):
                opponent_telegram = telegram_targets.get(opponent_user_id)
                if opponent_telegram is None:
                    failed_to += 1
                else:
                    try:
                        await bot.send_message(
                            chat_id=opponent_telegram,
                            text=(
                                "⌛ Dein Duell ist wegen Zeitablauf beendet.\n"
                                f"Finaler Score: Du {opponent_score} | Gegner {creator_score}."
                            ),
                            reply_markup=build_friend_challenge_finished_keyboard(
                                challenge_id=challenge_id
                            ),
                        )
                        sent_to += 1
                    except Exception:
                        failed_to += 1

            expired_notices_sent += sent_to
            expired_notices_failed += failed_to
            expired_notice_events.append(
                {
                    "challenge_id": challenge_id,
                    "sent_to": sent_to,
                    "failed_to": failed_to,
                    "creator_score": creator_score,
                    "opponent_score": opponent_score,
                }
            )
    finally:
        await bot.session.close()

    if reminder_events or expired_notice_events:
        async with SessionLocal.begin() as session:
            for payload in reminder_events:
                await emit_analytics_event(
                    session,
                    event_type="friend_challenge_last_chance_sent",
                    source=EVENT_SOURCE_WORKER,
                    happened_at=now_utc,
                    user_id=None,
                    payload=payload,
                )
            for payload in expired_notice_events:
                await emit_analytics_event(
                    session,
                    event_type="friend_challenge_expired_notice_sent",
                    source=EVENT_SOURCE_WORKER,
                    happened_at=now_utc,
                    user_id=None,
                    payload=payload,
                )

    result = {
        "batch_size": resolved_batch_size,
        "last_chance_queued_total": len(reminder_items),
        "expired_total": len(expired_items),
        "last_chance_sent_total": reminders_sent,
        "last_chance_failed_total": reminders_failed,
        "expired_notice_sent_total": expired_notices_sent,
        "expired_notice_failed_total": expired_notices_failed,
    }
    logger.info("friend_challenge_deadlines_processed", **result)
    return result


@celery_app.task(name="app.workers.tasks.friend_challenges.run_friend_challenge_deadlines")
def run_friend_challenge_deadlines(batch_size: int = DEADLINE_BATCH_SIZE) -> dict[str, int]:
    return run_async_job(run_friend_challenge_deadlines_async(batch_size=batch_size))


celery_app.conf.beat_schedule = celery_app.conf.beat_schedule or {}
celery_app.conf.beat_schedule.update(
    {
        "friend-challenge-deadlines-every-5-minutes": {
            "task": "app.workers.tasks.friend_challenges.run_friend_challenge_deadlines",
            "schedule": float(SCAN_INTERVAL_SECONDS),
            "options": {"queue": "q_normal"},
        },
    }
)
