from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.economy.streak.constants import BERLIN_TIMEZONE
from app.economy.streak.time import berlin_local_date
from app.game.sessions.errors import FriendChallengeAccessError

from .levels import _friend_challenge_level_for_round

_DUEL_FORMAT_ROUNDS: frozenset[int] = frozenset({5, 12})


def resolve_duel_rounds(*, total_rounds: int) -> int:
    resolved_rounds = int(total_rounds)
    if resolved_rounds not in _DUEL_FORMAT_ROUNDS:
        raise FriendChallengeAccessError
    return resolved_rounds


def berlin_day_start_utc(*, now_utc: datetime) -> datetime:
    berlin_zone = ZoneInfo(BERLIN_TIMEZONE)
    berlin_now = now_utc.astimezone(berlin_zone)
    return berlin_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


async def select_duel_question_ids(
    session: AsyncSession,
    *,
    mode_code: str,
    total_rounds: int,
    now_utc: datetime,
    challenge_seed: str,
) -> list[str]:
    from app.game.sessions import service as service_module

    local_date = berlin_local_date(now_utc)
    selected_ids: list[str] = []
    for round_no in range(1, total_rounds + 1):
        selected_question = await service_module.select_friend_challenge_question(
            session,
            mode_code,
            local_date_berlin=local_date,
            previous_round_question_ids=selected_ids,
            selection_seed=f"duel:{challenge_seed}:{round_no}",
            preferred_level=_friend_challenge_level_for_round(round_number=round_no),
        )
        selected_ids.append(selected_question.question_id)
    return selected_ids
