from __future__ import annotations

from collections.abc import Set as AbstractSet
from datetime import datetime
from typing import Any
from uuid import UUID


def empty_daily_cup_proof_cards_result() -> dict[str, int]:
    return {"processed": 0, "participants_total": 0, "sent": 0, "cached_reused": 0, "failed": 0}


async def load_daily_cup_proof_cards_runtime_context(
    *,
    parsed_tournament_id: UUID,
    user_id: int | None,
    now_utc: datetime,
    logger: Any,
    session_factory: Any,
    load_context_fn: Any,
    tournaments_repo: Any,
    users_repo: Any,
    matches_repo: Any,
    calculate_standings_fn: Any,
    format_points_fn: Any,
    format_user_label_fn: Any,
    is_today_daily_cup_tournament_fn: Any,
    daily_cup_tournament_types: AbstractSet[str],
    tournament_completed_status: str,
    timezone_name: str,
) -> Any:
    async with session_factory.begin() as session:
        return await load_context_fn(
            session=session,
            parsed_tournament_id=parsed_tournament_id,
            user_id=user_id,
            now_utc=now_utc,
            tournaments_repo=tournaments_repo,
            users_repo=users_repo,
            matches_repo=matches_repo,
            calculate_standings_fn=calculate_standings_fn,
            format_points_fn=format_points_fn,
            format_user_label_fn=format_user_label_fn,
            is_today_daily_cup_tournament_fn=is_today_daily_cup_tournament_fn,
            logger=logger,
            daily_cup_tournament_types=daily_cup_tournament_types,
            tournament_completed_status=tournament_completed_status,
            timezone_name=timezone_name,
        )


async def grant_daily_cup_winner_rewards_once(
    *,
    bot: Any,
    context: Any,
    tournament_id: str,
    now_utc: datetime,
    logger: Any,
    session_factory: Any,
    tournaments_repo: Any,
    grant_winner_rewards_fn: Any,
    send_reward_messages_fn: Any,
) -> list[Any]:
    try:
        async with session_factory.begin() as session:
            tournament_row = await tournaments_repo.get_by_id_for_update(
                session,
                context.parsed_tournament_id,
            )
            if tournament_row is None:
                return []
            notifications = await grant_winner_rewards_fn(
                session=session,
                context=context,
                now_utc=now_utc,
                logger=logger,
            )
            if notifications:
                await send_reward_messages_fn(
                    session=session,
                    bot=bot,
                    context=context,
                    notifications=notifications,
                    now_utc=now_utc,
                    logger=logger,
                )
            return notifications
    except Exception as exc:
        logger.warning(
            "daily_cup_winner_rewards_failed",
            tournament_id=tournament_id,
            error_type=type(exc).__name__,
        )
        return []
