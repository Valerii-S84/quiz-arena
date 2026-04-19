from __future__ import annotations

from datetime import datetime

from app.workers.tasks.friend_challenges_deadline_payloads import (
    ExpiredItem,
    ReminderItem,
    expired_item,
    expires_before_utc,
    last_chance_reminder_user_id,
    reminder_item,
)


async def queue_last_chance_reminders(
    session,
    *,
    now_utc: datetime,
    batch_size: int,
    repo,
) -> list[ReminderItem]:
    reminder_items: list[ReminderItem] = []
    due_last_chance = await repo.list_active_due_for_last_chance_for_update(
        session,
        now_utc=now_utc,
        expires_before_utc=expires_before_utc(now_utc=now_utc),
        limit=batch_size,
    )
    for challenge in due_last_chance:
        reminder_user_id = last_chance_reminder_user_id(challenge=challenge)
        if reminder_user_id is None:
            continue
        challenge.expires_last_chance_notified_at = now_utc
        challenge.updated_at = now_utc
        reminder_items.append(
            reminder_item(
                challenge=challenge,
                reminder_user_id=reminder_user_id,
            )
        )
    return reminder_items


async def collect_expired_items(
    session,
    *,
    now_utc: datetime,
    batch_size: int,
    repo,
    expire_friend_challenge_if_due,
    emit_duel_expired_event,
) -> list[ExpiredItem]:
    expired_items: list[ExpiredItem] = []
    pending_due = await repo.list_pending_due_for_expire_for_update(
        session,
        now_utc=now_utc,
        limit=batch_size,
    )
    joined_due = await repo.list_joined_due_for_walkover_for_update(
        session,
        now_utc=now_utc,
        limit=batch_size,
    )
    for challenge in [*pending_due, *joined_due]:
        previous_status = str(challenge.status)
        if not expire_friend_challenge_if_due(challenge=challenge, now_utc=now_utc):
            continue
        expired_notice = expired_item(
            challenge=challenge,
            previous_status=previous_status,
        )
        expired_items.append(expired_notice)
        await emit_duel_expired_event(
            session=session,
            expired_item=expired_notice,
        )
    return expired_items


async def collect_deadline_items(
    *,
    now_utc: datetime,
    batch_size: int,
    session_local,
    repo,
    expire_friend_challenge_if_due,
    emit_duel_expired_event,
) -> tuple[list[ReminderItem], list[ExpiredItem]]:
    async with session_local.begin() as session:
        reminder_items = await queue_last_chance_reminders(
            session,
            now_utc=now_utc,
            batch_size=batch_size,
            repo=repo,
        )
        expired_items = await collect_expired_items(
            session,
            now_utc=now_utc,
            batch_size=batch_size,
            repo=repo,
            expire_friend_challenge_if_due=expire_friend_challenge_if_due,
            emit_duel_expired_event=emit_duel_expired_event,
        )
    return reminder_items, expired_items
