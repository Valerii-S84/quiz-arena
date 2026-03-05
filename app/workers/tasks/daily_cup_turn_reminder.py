from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import structlog
from aiogram.exceptions import TelegramForbiddenError

from app.bot.application import build_bot
from app.bot.keyboards.daily_cup import build_daily_cup_lobby_keyboard
from app.bot.texts.de import TEXTS_DE
from app.db.models.friend_challenges import FriendChallenge
from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.friend_challenges.constants import DUEL_STATUS_CREATOR_DONE, DUEL_STATUS_OPPONENT_DONE
from app.workers.tasks.daily_cup_config import (
    DAILY_CUP_PUSH_BATCH_SIZE,
    DAILY_CUP_TURN_REMINDER_INTERVAL_MINUTES,
)
from app.workers.tasks.daily_cup_core import now_utc
from app.workers.tasks.daily_cup_push_events import store_push_sent_events
from app.workers.tasks.tournaments_messaging_text import format_deadline, format_user_label

logger = structlog.get_logger("app.workers.tasks.daily_cup_turn_reminder")

_REMINDER_EVENT_TYPE = "daily_cup_turn_reminder_sent"


@dataclass(frozen=True, slots=True)
class _ReminderItem:
    tournament_id: UUID
    challenge_id: str
    target_user_id: int
    target_chat_id: int
    opponent_label: str
    deadline_text: str


def resolve_turn_reminder_users(*, challenge: FriendChallenge) -> tuple[int, int] | None:
    if challenge.status == DUEL_STATUS_CREATOR_DONE and challenge.opponent_user_id is not None:
        return int(challenge.opponent_user_id), int(challenge.creator_user_id)
    if challenge.status == DUEL_STATUS_OPPONENT_DONE and challenge.opponent_user_id is not None:
        return int(challenge.creator_user_id), int(challenge.opponent_user_id)
    return None


def _build_turn_reminder_text(*, opponent_label: str, deadline_text: str) -> str:
    return TEXTS_DE["msg.daily_cup.turn_reminder"].format(
        opponent_label=opponent_label,
        deadline=deadline_text,
    )


async def run_daily_cup_turn_reminders_async(*, batch_size: int = DAILY_CUP_PUSH_BATCH_SIZE) -> dict[str, int]:
    now_utc_value = now_utc()
    remind_before_utc = now_utc_value - timedelta(minutes=DAILY_CUP_TURN_REMINDER_INTERVAL_MINUTES)
    resolved_batch_size = max(1, int(batch_size))

    scanned_total = sent_total = skipped_total = failed_total = 0
    reminders: list[_ReminderItem] = []

    async with SessionLocal.begin() as session:
        candidates = await TournamentMatchesRepo.list_daily_cup_turn_reminder_candidates_for_update(
            session,
            now_utc=now_utc_value,
            remind_before_utc=remind_before_utc,
            limit=resolved_batch_size,
        )
        if not candidates:
            result = {
                "processed": 1,
                "batch_size": resolved_batch_size,
                "scanned_total": 0,
                "queued_total": 0,
                "sent_total": 0,
                "skipped_total": 0,
                "failed_total": 0,
            }
            logger.info("daily_cup_turn_reminders_processed", **result)
            return result

        participant_user_ids: set[int] = set()
        for _match, challenge in candidates:
            resolved_users = resolve_turn_reminder_users(challenge=challenge)
            if resolved_users is None:
                continue
            target_user_id, opponent_user_id = resolved_users
            participant_user_ids.add(target_user_id)
            participant_user_ids.add(opponent_user_id)

        users = await UsersRepo.list_by_ids(session, list(participant_user_ids))
        user_labels = {
            int(user.id): format_user_label(username=user.username, first_name=user.first_name)
            for user in users
        }
        telegram_targets = {int(user.id): int(user.telegram_user_id) for user in users}

        queued_target_keys: set[tuple[UUID, int]] = set()
        for match, challenge in candidates:
            scanned_total += 1
            challenge.expires_last_chance_notified_at = now_utc_value
            challenge.updated_at = now_utc_value

            resolved_users = resolve_turn_reminder_users(challenge=challenge)
            if resolved_users is None:
                skipped_total += 1
                continue

            target_user_id, opponent_user_id = resolved_users
            target_chat_id = telegram_targets.get(target_user_id)
            if target_chat_id is None:
                skipped_total += 1
                continue
            target_key = (match.tournament_id, target_user_id)
            if target_key in queued_target_keys:
                skipped_total += 1
                continue
            queued_target_keys.add(target_key)

            reminders.append(
                _ReminderItem(
                    tournament_id=match.tournament_id,
                    challenge_id=str(challenge.id),
                    target_user_id=target_user_id,
                    target_chat_id=target_chat_id,
                    opponent_label=user_labels.get(opponent_user_id, "Spieler"),
                    deadline_text=format_deadline(match.deadline),
                )
            )

    sent_user_ids_by_tournament: dict[UUID, list[int]] = defaultdict(list)
    bot = build_bot()
    try:
        for reminder in reminders:
            keyboard = build_daily_cup_lobby_keyboard(
                tournament_id=str(reminder.tournament_id),
                can_join=False,
                play_challenge_id=reminder.challenge_id,
                show_share_result=False,
            )
            text = _build_turn_reminder_text(
                opponent_label=reminder.opponent_label,
                deadline_text=reminder.deadline_text,
            )
            try:
                await bot.send_message(
                    chat_id=reminder.target_chat_id,
                    text=text,
                    reply_markup=keyboard,
                )
                sent_total += 1
                sent_user_ids_by_tournament[reminder.tournament_id].append(reminder.target_user_id)
            except TelegramForbiddenError:
                failed_total += 1
            except Exception as exc:
                logger.warning(
                    "daily_cup_turn_reminder_send_failed",
                    challenge_id=reminder.challenge_id,
                    user_id=reminder.target_user_id,
                    error_type=type(exc).__name__,
                )
                failed_total += 1
    finally:
        await bot.session.close()

    for tournament_id, sent_user_ids in sent_user_ids_by_tournament.items():
        try:
            await store_push_sent_events(
                event_type=_REMINDER_EVENT_TYPE,
                tournament_id=tournament_id,
                user_ids=sent_user_ids,
                happened_at=now_utc_value,
            )
        except Exception as exc:
            logger.warning(
                "daily_cup_turn_reminder_event_store_failed",
                tournament_id=str(tournament_id),
                sent_total=len(sent_user_ids),
                error_type=type(exc).__name__,
            )

    result = {
        "processed": 1,
        "batch_size": resolved_batch_size,
        "scanned_total": scanned_total,
        "queued_total": len(reminders),
        "sent_total": sent_total,
        "skipped_total": skipped_total,
        "failed_total": failed_total,
    }
    logger.info("daily_cup_turn_reminders_processed", **result)
    return result


__all__ = ["resolve_turn_reminder_users", "run_daily_cup_turn_reminders_async"]
