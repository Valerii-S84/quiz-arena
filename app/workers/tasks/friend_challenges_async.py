from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog

from app.core.analytics_events import EVENT_SOURCE_WORKER, emit_analytics_event
from app.db.repo.friend_challenges_repo import FriendChallengesRepo
from app.db.session import SessionLocal
from app.game.friend_challenges.constants import DUEL_STATUS_CREATOR_DONE, DUEL_STATUS_OPPONENT_DONE
from app.game.sessions.service.constants import DUEL_MAX_PUSH_PER_USER
from app.game.sessions.service.friend_challenges_internal import _expire_friend_challenge_if_due
from app.workers.tasks.friend_challenges_config import DEADLINE_BATCH_SIZE, LAST_CHANCE_SECONDS
from app.workers.tasks.friend_challenges_notifications import send_deadline_notifications

logger = structlog.get_logger("app.workers.tasks.friend_challenges")


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
            reminder_user_id: int | None = None
            if (
                challenge.status == DUEL_STATUS_CREATOR_DONE
                and challenge.opponent_user_id is not None
                and challenge.opponent_push_count < DUEL_MAX_PUSH_PER_USER
            ):
                challenge.opponent_push_count += 1
                reminder_user_id = int(challenge.opponent_user_id)
            elif (
                challenge.status == DUEL_STATUS_OPPONENT_DONE
                and challenge.creator_push_count < DUEL_MAX_PUSH_PER_USER
            ):
                challenge.creator_push_count += 1
                reminder_user_id = int(challenge.creator_user_id)
            if reminder_user_id is None:
                continue
            challenge.expires_last_chance_notified_at = now_utc
            challenge.updated_at = now_utc
            reminder_items.append(
                {
                    "challenge_id": str(challenge.id),
                    "target_user_id": reminder_user_id,
                    "creator_user_id": int(challenge.creator_user_id),
                    "opponent_user_id": (
                        int(challenge.opponent_user_id)
                        if challenge.opponent_user_id is not None
                        else None
                    ),
                    "status": challenge.status,
                    "expires_at": challenge.expires_at,
                }
            )

        pending_due = await FriendChallengesRepo.list_pending_due_for_expire_for_update(
            session,
            now_utc=now_utc,
            limit=resolved_batch_size,
        )
        joined_due = await FriendChallengesRepo.list_joined_due_for_walkover_for_update(
            session,
            now_utc=now_utc,
            limit=resolved_batch_size,
        )
        for challenge in [*pending_due, *joined_due]:
            previous_status = str(challenge.status)
            expired_now = _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc)
            if not expired_now:
                continue
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
                    "winner_user_id": (
                        int(challenge.winner_user_id)
                        if challenge.winner_user_id is not None
                        else None
                    ),
                    "status": challenge.status,
                    "previous_status": previous_status,
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
                    "winner_user_id": (
                        int(challenge.winner_user_id)
                        if challenge.winner_user_id is not None
                        else None
                    ),
                    "status": challenge.status,
                    "previous_status": previous_status,
                    "total_rounds": int(challenge.total_rounds),
                    "expires_at": challenge.expires_at.isoformat(),
                },
            )

    (
        reminders_sent,
        reminders_failed,
        expired_notices_sent,
        expired_notices_failed,
        reminder_events,
        expired_notice_events,
    ) = await send_deadline_notifications(
        now_utc=now_utc,
        reminder_items=reminder_items,
        expired_items=expired_items,
    )

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
