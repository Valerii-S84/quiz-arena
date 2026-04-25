from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.bot.texts.de import TEXTS_DE
from app.core.analytics_events import EVENT_SOURCE_WORKER, emit_analytics_event
from app.db.repo.analytics_repo import AnalyticsRepo
from app.workers.tasks.daily_cup_winner_reward_grants import grant_daily_cup_rank_reward

DAILY_CUP_REWARD_MIN_PARTICIPANTS = 13
_WINNER_REWARD_MESSAGE_SENT = "daily_cup_winner_reward_message_sent"


@dataclass(frozen=True, slots=True)
class DailyCupWinnerRewardNotification:
    user_id: int
    text: str


async def grant_daily_cup_winner_rewards(
    *,
    session: Any,
    context: Any,
    now_utc: datetime,
    logger: Any,
) -> list[DailyCupWinnerRewardNotification]:
    if context.participants_total < DAILY_CUP_REWARD_MIN_PARTICIPANTS:
        return []

    participant_user_ids = {int(row.user_id) for row in context.participants}
    winner_user_ids = [
        int(user_id)
        for user_id in context.standings_user_ids[:3]
        if int(user_id) in participant_user_ids
    ]
    already_notified = await AnalyticsRepo.list_user_ids_by_event_type_and_tournament(
        session,
        event_type=_WINNER_REWARD_MESSAGE_SENT,
        tournament_id=str(context.parsed_tournament_id),
        user_ids=winner_user_ids,
    )

    notifications: list[DailyCupWinnerRewardNotification] = []
    for rank, current_user_id in enumerate(context.standings_user_ids[:3], start=1):
        if current_user_id not in participant_user_ids:
            continue
        reward_ready = await grant_daily_cup_rank_reward(
            session=session,
            tournament_id=context.parsed_tournament_id,
            user_id=current_user_id,
            rank=rank,
            now_utc=now_utc,
            logger=logger,
        )
        if reward_ready and current_user_id not in already_notified:
            notifications.append(
                DailyCupWinnerRewardNotification(
                    user_id=current_user_id,
                    text=TEXTS_DE[f"msg.daily_cup.reward.rank_{rank}"],
                )
            )
    return notifications


async def send_daily_cup_winner_reward_messages(
    *,
    session: Any,
    bot: Any,
    context: Any,
    notifications: list[DailyCupWinnerRewardNotification],
    now_utc: datetime,
    logger: Any,
) -> None:
    for notification in notifications:
        chat_id = context.telegram_targets.get(notification.user_id)
        if chat_id is None:
            continue
        try:
            await bot.send_message(chat_id=chat_id, text=notification.text)
            await emit_analytics_event(
                session,
                event_type=_WINNER_REWARD_MESSAGE_SENT,
                source=EVENT_SOURCE_WORKER,
                happened_at=now_utc,
                user_id=notification.user_id,
                payload={"tournament_id": str(context.parsed_tournament_id)},
            )
        except Exception as exc:
            logger.warning(
                "daily_cup_winner_reward_message_failed",
                tournament_id=str(context.parsed_tournament_id),
                user_id=notification.user_id,
                error_type=type(exc).__name__,
            )


__all__ = [
    "DAILY_CUP_REWARD_MIN_PARTICIPANTS",
    "DailyCupWinnerRewardNotification",
    "grant_daily_cup_winner_rewards",
    "send_daily_cup_winner_reward_messages",
]
