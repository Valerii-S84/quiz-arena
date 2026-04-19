from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram.types import CallbackQuery

from app.bot.handlers.gameplay_flows.friend_answer_completion_delivery import (
    Answerable,
    resolve_answerable,
)
from app.bot.handlers.gameplay_flows.friend_answer_completion_state import (
    FriendSeriesContext,
    resolve_friend_series_context,
)


@dataclass(frozen=True, slots=True)
class FriendCompletionContext:
    answerable: Answerable
    series_context: FriendSeriesContext


async def resolve_completion_context(
    callback: CallbackQuery,
    *,
    challenge,
    snapshot_user_id: int,
    opponent_label: str,
    now_utc: datetime,
    session_local,
    game_session_service,
) -> FriendCompletionContext:
    return FriendCompletionContext(
        answerable=resolve_answerable(callback),
        series_context=await resolve_friend_series_context(
            challenge=challenge,
            snapshot_user_id=snapshot_user_id,
            opponent_label=opponent_label,
            now_utc=now_utc,
            session_local=session_local,
            game_session_service=game_session_service,
        ),
    )
