from __future__ import annotations

from datetime import datetime, timedelta
from typing import TypedDict

from app.game.friend_challenges.constants import DUEL_STATUS_CREATOR_DONE, DUEL_STATUS_OPPONENT_DONE
from app.game.sessions.service.constants import DUEL_MAX_PUSH_PER_USER
from app.workers.tasks.friend_challenges_config import LAST_CHANCE_SECONDS


class ReminderItem(TypedDict):
    challenge_id: str
    target_user_id: int
    creator_user_id: int
    opponent_user_id: int | None
    status: str
    expires_at: datetime


class ExpiredItem(TypedDict):
    challenge_id: str
    creator_user_id: int
    opponent_user_id: int | None
    creator_score: int
    opponent_score: int
    total_rounds: int
    winner_user_id: int | None
    status: str
    previous_status: str
    expires_at: datetime


def resolved_deadline_batch_size(*, batch_size: int) -> int:
    return max(1, int(batch_size))


def expires_before_utc(*, now_utc: datetime) -> datetime:
    return now_utc + timedelta(seconds=LAST_CHANCE_SECONDS)


def last_chance_reminder_user_id(*, challenge) -> int | None:
    if (
        challenge.status == DUEL_STATUS_CREATOR_DONE
        and challenge.opponent_user_id is not None
        and challenge.opponent_push_count < DUEL_MAX_PUSH_PER_USER
    ):
        challenge.opponent_push_count += 1
        return int(challenge.opponent_user_id)
    if (
        challenge.status == DUEL_STATUS_OPPONENT_DONE
        and challenge.creator_push_count < DUEL_MAX_PUSH_PER_USER
    ):
        challenge.creator_push_count += 1
        return int(challenge.creator_user_id)
    return None


def reminder_item(*, challenge, reminder_user_id: int) -> ReminderItem:
    return {
        "challenge_id": str(challenge.id),
        "target_user_id": reminder_user_id,
        "creator_user_id": int(challenge.creator_user_id),
        "opponent_user_id": (
            int(challenge.opponent_user_id) if challenge.opponent_user_id is not None else None
        ),
        "status": challenge.status,
        "expires_at": challenge.expires_at,
    }


def expired_item(*, challenge, previous_status: str) -> ExpiredItem:
    return {
        "challenge_id": str(challenge.id),
        "creator_user_id": int(challenge.creator_user_id),
        "opponent_user_id": (
            int(challenge.opponent_user_id) if challenge.opponent_user_id is not None else None
        ),
        "creator_score": int(challenge.creator_score),
        "opponent_score": int(challenge.opponent_score),
        "total_rounds": int(challenge.total_rounds),
        "winner_user_id": (
            int(challenge.winner_user_id) if challenge.winner_user_id is not None else None
        ),
        "status": challenge.status,
        "previous_status": previous_status,
        "expires_at": challenge.expires_at,
    }


def duel_expired_payload(*, expired_item: ExpiredItem) -> dict[str, object]:
    return {
        **expired_item,
        "expires_at": expired_item["expires_at"].isoformat(),
    }


def deadline_result(
    *,
    batch_size: int,
    reminder_items: list[ReminderItem],
    expired_items: list[ExpiredItem],
    reminders_sent: int,
    reminders_failed: int,
    expired_notices_sent: int,
    expired_notices_failed: int,
) -> dict[str, int]:
    return {
        "batch_size": batch_size,
        "last_chance_queued_total": len(reminder_items),
        "expired_total": len(expired_items),
        "last_chance_sent_total": reminders_sent,
        "last_chance_failed_total": reminders_failed,
        "expired_notice_sent_total": expired_notices_sent,
        "expired_notice_failed_total": expired_notices_failed,
    }
