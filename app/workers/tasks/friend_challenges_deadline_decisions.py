from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.game.friend_challenges.constants import (
    DUEL_STATUS_CREATOR_DONE,
    DUEL_STATUS_OPPONENT_DONE,
    DUEL_STATUS_PENDING,
)
from app.game.sessions.service.constants import DUEL_MAX_PUSH_PER_USER
from app.game.sessions.service.friend_challenges_internal import _expire_friend_challenge_if_due
from app.workers.tasks.friend_challenges_deadline_types import (
    DeadlinePayload,
    FriendChallengeDeadlineContext,
    FriendChallengeDeadlineWork,
)

if TYPE_CHECKING:
    from app.db.models.friend_challenges import FriendChallenge


@dataclass(frozen=True)
class LastChanceReminderDecision:
    target_user_id: int
    reminder_kind: str
    push_counter: str


def queue_last_chance_reminders(
    *,
    context: FriendChallengeDeadlineContext,
    work: FriendChallengeDeadlineWork,
    challenges: list[FriendChallenge],
) -> None:
    for challenge in challenges:
        item = _claim_last_chance_reminder(challenge, now_utc=context.now_utc)
        if item is not None:
            work.reminder_items.append(item)


def _claim_last_chance_reminder(
    challenge: FriendChallenge,
    *,
    now_utc: datetime,
) -> DeadlinePayload | None:
    decision = _last_chance_reminder_decision(challenge)
    if decision is None:
        return None
    _mark_last_chance_reminder(challenge, decision=decision, now_utc=now_utc)
    return _build_reminder_item(challenge, decision=decision)


def _last_chance_reminder_decision(
    challenge: FriendChallenge,
) -> LastChanceReminderDecision | None:
    if _is_unplayed_reminder_due(challenge):
        return LastChanceReminderDecision(
            target_user_id=int(challenge.creator_user_id),
            reminder_kind="unplayed",
            push_counter="creator",
        )
    if _is_opponent_turn_reminder_due(challenge):
        return LastChanceReminderDecision(
            target_user_id=_required_int(challenge.opponent_user_id),
            reminder_kind="turn",
            push_counter="opponent",
        )
    if _is_creator_turn_reminder_due(challenge):
        return LastChanceReminderDecision(
            target_user_id=int(challenge.creator_user_id),
            reminder_kind="turn",
            push_counter="creator",
        )
    return None


def _is_unplayed_reminder_due(challenge: FriendChallenge) -> bool:
    return (
        challenge.status == DUEL_STATUS_PENDING
        and challenge.opponent_user_id is None
        and challenge.creator_push_count < DUEL_MAX_PUSH_PER_USER
    )


def _is_opponent_turn_reminder_due(challenge: FriendChallenge) -> bool:
    return (
        challenge.status == DUEL_STATUS_CREATOR_DONE
        and challenge.opponent_user_id is not None
        and challenge.opponent_push_count < DUEL_MAX_PUSH_PER_USER
    )


def _is_creator_turn_reminder_due(challenge: FriendChallenge) -> bool:
    return (
        challenge.status == DUEL_STATUS_OPPONENT_DONE
        and challenge.creator_push_count < DUEL_MAX_PUSH_PER_USER
    )


def _mark_last_chance_reminder(
    challenge: FriendChallenge,
    *,
    decision: LastChanceReminderDecision,
    now_utc: datetime,
) -> None:
    if decision.push_counter == "creator":
        challenge.creator_push_count += 1
    else:
        challenge.opponent_push_count += 1
    challenge.expires_last_chance_notified_at = now_utc
    challenge.updated_at = now_utc


def _build_reminder_item(
    challenge: FriendChallenge,
    *,
    decision: LastChanceReminderDecision,
) -> DeadlinePayload:
    return {
        "challenge_id": str(challenge.id),
        "target_user_id": decision.target_user_id,
        "creator_user_id": int(challenge.creator_user_id),
        "opponent_user_id": _optional_int(challenge.opponent_user_id),
        "status": challenge.status,
        "expires_at": challenge.expires_at,
        "reminder_kind": decision.reminder_kind,
    }


def expire_due_challenge(
    challenge: FriendChallenge,
    *,
    now_utc: datetime,
) -> DeadlinePayload | None:
    previous_status = str(challenge.status)
    expired_now = _expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc)
    if not expired_now:
        return None
    return _build_expired_item(challenge, previous_status=previous_status)


def _build_expired_item(
    challenge: FriendChallenge,
    *,
    previous_status: str,
) -> DeadlinePayload:
    return {
        "challenge_id": str(challenge.id),
        "creator_user_id": int(challenge.creator_user_id),
        "opponent_user_id": _optional_int(challenge.opponent_user_id),
        "creator_score": int(challenge.creator_score),
        "opponent_score": int(challenge.opponent_score),
        "total_rounds": int(challenge.total_rounds),
        "winner_user_id": _optional_int(challenge.winner_user_id),
        "status": challenge.status,
        "previous_status": previous_status,
        "expires_at": challenge.expires_at,
    }


def _required_int(value: Any | None) -> int:
    if value is None:
        raise ValueError("Expected non-null integer value")
    return int(value)


def _optional_int(value: Any | None) -> int | None:
    return int(value) if value is not None else None
