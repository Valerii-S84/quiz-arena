from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.tasks.friend_challenges_config import LAST_CHANCE_SECONDS
from app.workers.tasks.friend_challenges_deadline_decisions import (
    expire_due_challenge,
    queue_last_chance_reminders,
)
from app.workers.tasks.friend_challenges_deadline_events import (
    AnalyticsEmitter,
    emit_duel_expired_event,
    emit_notification_event,
)
from app.workers.tasks.friend_challenges_deadline_types import (
    DeadlineNotificationResult,
    FriendChallengeDeadlineContext,
    FriendChallengeDeadlineWork,
)

DeadlineNotificationSender = Callable[..., Awaitable[tuple[int, int, int, int, list, list]]]


def build_deadline_context(*, batch_size: int) -> FriendChallengeDeadlineContext:
    now_utc = datetime.now(timezone.utc)
    return FriendChallengeDeadlineContext(
        now_utc=now_utc,
        expires_before_utc=now_utc + timedelta(seconds=LAST_CHANCE_SECONDS),
        batch_size=max(1, int(batch_size)),
    )


async def collect_deadline_work(
    session: AsyncSession,
    *,
    context: FriendChallengeDeadlineContext,
    challenges_repo: Any,
    emit_event: AnalyticsEmitter,
) -> FriendChallengeDeadlineWork:
    work = FriendChallengeDeadlineWork(reminder_items=[], expired_items=[])
    last_chance_candidates = await load_last_chance_candidates(
        session,
        context=context,
        challenges_repo=challenges_repo,
    )
    queue_last_chance_reminders(
        context=context,
        work=work,
        challenges=last_chance_candidates,
    )
    expired_candidates = await load_expired_candidates(
        session,
        context=context,
        challenges_repo=challenges_repo,
    )
    await queue_expired_challenges(
        session,
        context=context,
        work=work,
        challenges=expired_candidates,
        emit_event=emit_event,
    )
    return work


async def load_last_chance_candidates(
    session: AsyncSession,
    *,
    context: FriendChallengeDeadlineContext,
    challenges_repo: Any,
) -> list:
    return await challenges_repo.list_active_due_for_last_chance_for_update(
        session,
        now_utc=context.now_utc,
        expires_before_utc=context.expires_before_utc,
        limit=context.batch_size,
    )


async def load_expired_candidates(
    session: AsyncSession,
    *,
    context: FriendChallengeDeadlineContext,
    challenges_repo: Any,
) -> list:
    pending_due = await challenges_repo.list_pending_due_for_expire_for_update(
        session,
        now_utc=context.now_utc,
        limit=context.batch_size,
    )
    joined_due = await challenges_repo.list_joined_due_for_walkover_for_update(
        session,
        now_utc=context.now_utc,
        limit=context.batch_size,
    )
    return [*pending_due, *joined_due]


async def queue_expired_challenges(
    session: AsyncSession,
    *,
    context: FriendChallengeDeadlineContext,
    work: FriendChallengeDeadlineWork,
    challenges: list,
    emit_event: AnalyticsEmitter,
) -> None:
    for challenge in challenges:
        item = expire_due_challenge(challenge, now_utc=context.now_utc)
        if item is None:
            continue
        work.expired_items.append(item)
        await emit_duel_expired_event(
            session,
            item=item,
            happened_at=context.now_utc,
            emit_event=emit_event,
        )


async def send_deadline_notifications_for_work(
    *,
    context: FriendChallengeDeadlineContext,
    work: FriendChallengeDeadlineWork,
    send_notifications: DeadlineNotificationSender,
) -> DeadlineNotificationResult:
    (
        reminders_sent,
        reminders_failed,
        expired_notices_sent,
        expired_notices_failed,
        reminder_events,
        expired_notice_events,
    ) = await send_notifications(
        now_utc=context.now_utc,
        reminder_items=work.reminder_items,
        expired_items=work.expired_items,
    )
    return DeadlineNotificationResult(
        reminders_sent=reminders_sent,
        reminders_failed=reminders_failed,
        expired_notices_sent=expired_notices_sent,
        expired_notices_failed=expired_notices_failed,
        reminder_events=reminder_events,
        expired_notice_events=expired_notice_events,
    )


async def emit_notification_events(
    *,
    context: FriendChallengeDeadlineContext,
    notification_result: DeadlineNotificationResult,
    session_factory: Any,
    emit_event: AnalyticsEmitter,
) -> None:
    if not notification_result.has_events:
        return
    async with session_factory.begin() as session:
        await emit_deadline_notification_events(
            session,
            context=context,
            notification_result=notification_result,
            emit_event=emit_event,
        )


async def emit_deadline_notification_events(
    session: AsyncSession,
    *,
    context: FriendChallengeDeadlineContext,
    notification_result: DeadlineNotificationResult,
    emit_event: AnalyticsEmitter,
) -> None:
    for payload in notification_result.reminder_events:
        await emit_notification_event(
            session,
            event_type="friend_challenge_last_chance_sent",
            payload=payload,
            happened_at=context.now_utc,
            emit_event=emit_event,
        )
    for payload in notification_result.expired_notice_events:
        await emit_notification_event(
            session,
            event_type="friend_challenge_expired_notice_sent",
            payload=payload,
            happened_at=context.now_utc,
            emit_event=emit_event,
        )
