from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.db.repo.tournament_matches_repo import TournamentMatchesRepo
from app.db.repo.tournaments_repo import TournamentsRepo
from app.db.repo.users_repo import UsersRepo
from app.db.session import SessionLocal
from app.game.tournaments.constants import DAILY_CUP_TOURNAMENT_TYPES, TOURNAMENT_STATUS_COMPLETED
from app.game.tournaments.daily_cup_standings import calculate_daily_cup_standings
from app.workers.tasks.daily_cup_config import DAILY_CUP_TIMEZONE
from app.workers.tasks.daily_cup_proof_cards_context import load_daily_cup_proof_cards_context
from app.workers.tasks.daily_cup_proof_cards_text import format_points, format_user_label
from app.workers.tasks.daily_cup_task_helpers import is_today_daily_cup_tournament
from app.workers.tasks.daily_cup_winner_rewards import (
    grant_daily_cup_winner_rewards,
    send_daily_cup_winner_reward_messages,
)


def empty_daily_cup_proof_cards_result() -> dict[str, int]:
    return {"processed": 0, "participants_total": 0, "sent": 0, "cached_reused": 0, "failed": 0}


async def load_daily_cup_proof_cards_runtime_context(
    *,
    parsed_tournament_id: UUID,
    user_id: int | None,
    now_utc: datetime,
    logger: Any,
) -> Any:
    async with SessionLocal.begin() as session:
        return await load_daily_cup_proof_cards_context(
            session=session,
            parsed_tournament_id=parsed_tournament_id,
            user_id=user_id,
            now_utc=now_utc,
            tournaments_repo=TournamentsRepo,
            users_repo=UsersRepo,
            matches_repo=TournamentMatchesRepo,
            calculate_standings_fn=calculate_daily_cup_standings,
            format_points_fn=format_points,
            format_user_label_fn=format_user_label,
            is_today_daily_cup_tournament_fn=is_today_daily_cup_tournament,
            logger=logger,
            daily_cup_tournament_types=DAILY_CUP_TOURNAMENT_TYPES,
            tournament_completed_status=TOURNAMENT_STATUS_COMPLETED,
            timezone_name=DAILY_CUP_TIMEZONE,
        )


async def grant_daily_cup_winner_rewards_once(
    *,
    bot: Any,
    context: Any,
    tournament_id: str,
    now_utc: datetime,
    logger: Any,
) -> list[Any]:
    try:
        async with SessionLocal.begin() as session:
            tournament_row = await TournamentsRepo.get_by_id_for_update(
                session,
                context.parsed_tournament_id,
            )
            if tournament_row is None:
                return []
            notifications = await grant_daily_cup_winner_rewards(
                session=session,
                context=context,
                now_utc=now_utc,
                logger=logger,
            )
            if notifications:
                await send_daily_cup_winner_reward_messages(
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
