from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from aiogram.types import CallbackQuery

from app.game.arena_duels.analytics import (
    ARENA_EVENT_DUEL_LIMIT_HIT,
    ARENA_EVENT_DUEL_PAYWALL_SHOWN,
    build_arena_event_payload,
    emit_arena_analytics_event,
    with_paywall_context,
)
from app.game.arena_duels.errors import (
    ArenaDuelAccessError,
    ArenaDuelAlreadyAttemptedError,
    ArenaDuelExpiredError,
    ArenaDuelNotFoundError,
    ArenaDuelOwnAttemptError,
    ArenaDuelPaymentRequiredError,
)
from app.game.sessions.errors import FriendChallengeAccessError


@dataclass(frozen=True, slots=True)
class ArenaStartOutcome:
    snapshot: Any
    result: object | None = None
    guard_text_key: str | None = None
    payment_required: bool = False


async def resolve_arena_start_outcome(
    callback: CallbackQuery,
    *,
    session_local,
    user_onboarding_service,
    resolve_access_type,
    start_arena_round: Callable[[object, int, datetime, str], Awaitable[object]],
    now_utc: datetime,
) -> ArenaStartOutcome:
    async with session_local.begin() as session:
        snapshot = await user_onboarding_service.ensure_home_snapshot(
            session,
            telegram_user=callback.from_user,
        )
        try:
            access_type = await resolve_access_type(
                session, user_id=snapshot.user_id, now_utc=now_utc
            )
            result = await start_arena_round(session, snapshot.user_id, now_utc, access_type)
        except ArenaDuelPaymentRequiredError:
            action = _arena_action_from_callback_data(callback.data)
            await _emit_arena_limit_events(
                session,
                user_id=snapshot.user_id,
                action=action,
                now_utc=now_utc,
            )
            return ArenaStartOutcome(snapshot=snapshot, payment_required=True)
        except ArenaDuelOwnAttemptError:
            return ArenaStartOutcome(snapshot=snapshot, guard_text_key="msg.duels.arena.own")
        except ArenaDuelAlreadyAttemptedError:
            return ArenaStartOutcome(
                snapshot=snapshot,
                guard_text_key="msg.duels.arena.already_played",
            )
        except (
            ArenaDuelExpiredError,
            ArenaDuelNotFoundError,
            ArenaDuelAccessError,
            FriendChallengeAccessError,
        ):
            return ArenaStartOutcome(snapshot=snapshot, guard_text_key="msg.duels.arena.expired")
    return ArenaStartOutcome(snapshot=snapshot, result=result)


async def _emit_arena_limit_events(
    session,
    *,
    user_id: int,
    action: str,
    now_utc: datetime,
) -> None:
    payload = with_paywall_context(
        build_arena_event_payload(user_id=user_id, action=action),
        "arena_limit",
    )
    for event_type in (ARENA_EVENT_DUEL_LIMIT_HIT, ARENA_EVENT_DUEL_PAYWALL_SHOWN):
        await emit_arena_analytics_event(
            session,
            event_type=event_type,
            happened_at=now_utc,
            user_id=user_id,
            payload=payload,
        )


def _arena_action_from_callback_data(callback_data: str | None) -> str:
    if callback_data == "arena:start_create":
        return "create"
    if callback_data is not None and callback_data.startswith("arena:start_attempt:"):
        return "accept"
    return "arena"
