from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

DeadlinePayload = dict[str, object]


@dataclass(frozen=True)
class FriendChallengeDeadlineContext:
    now_utc: datetime
    expires_before_utc: datetime
    batch_size: int


@dataclass
class FriendChallengeDeadlineWork:
    reminder_items: list[DeadlinePayload]
    expired_items: list[DeadlinePayload]


@dataclass(frozen=True)
class DeadlineNotificationResult:
    reminders_sent: int
    reminders_failed: int
    expired_notices_sent: int
    expired_notices_failed: int
    reminder_events: list[DeadlinePayload]
    expired_notice_events: list[DeadlinePayload]

    @property
    def has_events(self) -> bool:
        return bool(self.reminder_events or self.expired_notice_events)


def build_deadline_result(
    *,
    context: FriendChallengeDeadlineContext,
    work: FriendChallengeDeadlineWork,
    notification_result: DeadlineNotificationResult,
) -> dict[str, int]:
    return {
        "batch_size": context.batch_size,
        "last_chance_queued_total": len(work.reminder_items),
        "expired_total": len(work.expired_items),
        "last_chance_sent_total": notification_result.reminders_sent,
        "last_chance_failed_total": notification_result.reminders_failed,
        "expired_notice_sent_total": notification_result.expired_notices_sent,
        "expired_notice_failed_total": notification_result.expired_notices_failed,
    }
